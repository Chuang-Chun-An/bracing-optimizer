from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from dxf_import.dialog import DXFImportDialog
from dxf_import.geometry import (
    _line_distance,
    _line_segment_intersection_point,
    _line_separation,
    _supporting_line_separation,
)
from dxf_import.importer import (
    DXFImporter,
    Y05_LAYER_MAPPING,
    Y1A_LAYER_MAPPING,
    Y29_LAYER_MAPPING,
)
from dxf_import.models import DXFImportResult, ExcludedSource, GeometryTolerances
from dxf_import.material_recognition import (
    recognize_material_spec_from_width,
    recognize_result_material_specs,
)
from dxf_import.recognition import (
    _Candidate,
    _candidate_from_group,
    _resolve_waler_contact_geometry,
    _waler_source_width_assessment,
)
from dxf_import.validation import build_problem_records, build_review_items
from dxf_import.waler_contact_face import (
    BraceTerminalStatus,
    MemberGeometryFacts,
    MemberTerminalEvidence,
    TerminalIdentityState,
    TerminalTopologyIssue,
    TerminalTopologyOutcome,
    WalerContactOutcome,
    WalerContactIssue,
    WalerContactResolution,
    WalerEnvelopeFacts,
    WalerEnvelopeStatus,
    build_brace_terminal_verdicts,
    build_member_terminal_evidence,
    extract_waler_envelope_facts,
    find_significant_waler_overlaps,
    find_waler_overlap_competitions,
    resolve_waler_contact_faces,
)
from tests.sample_dxf_assets import Y05_DXF_PATH, Y1A_DXF_PATH, Y29_DXF_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
Point = tuple[float, float]
Segment = tuple[Point, Point]

WALER_MATERIAL_SPECS = (
    {"Usage": "圍令", "Spec": "H350x350"},
    {"Usage": "圍令", "Spec": "H400x400"},
    {"Usage": "圍令", "Spec": "H400x408"},
    {"Usage": "圍令", "Spec": "H414x405"},
    {"Usage": "圍令", "Spec": "H428x407"},
    {"Usage": "圍令", "Spec": "H458x417"},
)

# source handle -> (legacy finite-segment width, supporting-line width,
#                    legacy material, corrected material, general gate applies)
WALER_WIDTH_CHARACTERIZATION = {
    "Y05": {
        "971": (312.0, 312.0, "", "", True),
        "97D": (350.0, 350.0, "H350x350", "H350x350", True),
        "989": (350.0, 350.0, "H350x350", "H350x350", True),
        "B1D": (312.0, 312.0, "", "", True),
        "B29": (350.0, 350.0, "H350x350", "H350x350", True),
        "B34": (331.0, 331.0, "", "", True),
        "C86": (350.0, 350.0, "H350x350", "H350x350", True),
        "C90": (350.0, 350.0, "H350x350", "H350x350", True),
        "C72": (0.0, 0.0, "", "", False),
        "CA2": (0.0, 0.0, "", "", False),
        "ABE": (100.0, 100.0, "RC", "RC", False),
        "C97": (100.0, 100.0, "RC", "RC", False),
        "E65": (800.0, 800.0, "RC", "RC", False),
        "163D": (800.0, 800.0, "RC", "RC", False),
        "1647": (800.0, 800.0, "RC", "RC", False),
        "1650": (800.0, 800.0, "RC", "RC", False),
    },
    "Y29": {
        "74": (400.000056, 400.000056, "H400x400", "H400x400", True),
        "76": (400.0, 400.0, "H400x400", "H400x400", True),
        "F4": (400.0, 400.0, "H400x400", "H400x400", True),
        "193": (400.0, 400.0, "H400x400", "H400x400", True),
        "211": (400.0, 400.0, "H400x400", "H400x400", True),
        "232": (400.0, 400.0, "H400x400", "H400x400", True),
        "25E": (400.010038, 400.010038, "H400x400", "H400x400", True),
        "260": (400.009678, 400.009678, "H400x400", "H400x400", True),
        "284": (400.0, 400.0, "H400x400", "H400x400", True),
        "43F": (400.000128, 400.000128, "H400x400", "H400x400", True),
        "4BC": (400.0, 400.0, "H400x400", "H400x400", True),
        "4E4": (400.0, 400.0, "H400x400", "H400x400", True),
        "4E5": (400.0, 400.0, "H400x400", "H400x400", True),
        "58D": (400.0, 400.0, "H400x400", "H400x400", True),
        "603": (400.0, 400.0, "H400x400", "H400x400", True),
        "63D": (400.0, 400.0, "H400x400", "H400x400", True),
        "69C": (400.0, 400.0, "H400x400", "H400x400", True),
        "69F": (404.681630, 400.000099, "H414x405", "H400x400", True),
        "720": (400.0, 400.0, "H400x400", "H400x400", True),
        "721": (400.0, 400.0, "H400x400", "H400x400", True),
    },
    "Y1A": {
        "CE83A": (350.0, 350.0, "H350x350", "H350x350", True),
        "CE83B": (350.0, 350.0, "H350x350", "H350x350", True),
        "CE83C": (350.0, 350.0, "H350x350", "H350x350", True),
        "CE83D": (349.948428, 349.948426, "H350x350", "H350x350", True),
    },
}


def _internal_layer_roles(importer: DXFImporter, mapping: dict[str, str]) -> dict[str, str]:
    return {
        layer: DXFImportDialog.USE_TO_ROLE[label]
        for layer, label in mapping.items()
        if layer in importer.layer_names
    }


def _role_layer(layer_roles: dict[str, str], role: str) -> str:
    return next(layer for layer, mapped_role in layer_roles.items() if mapped_role == role)


def _candidate_groups(
    importer: DXFImporter,
    layer_roles: dict[str, str],
    role: str,
):
    layer = _role_layer(layer_roles, role)
    groups = importer._geometry_groups(
        role,
        layer,
        importer.entities_on_layer(layer),
        [],
        [],
    )
    return importer._merge_related_line_groups(groups, importer.tolerances)


def _axis_normal(line: Segment) -> Point:
    dx = line[1][0] - line[0][0]
    dy = line[1][1] - line[0][1]
    length = math.hypot(dx, dy)
    return -dy / length, dx / length


def _project_to_infinite_line(point: Point, line: Segment) -> Point:
    dx = line[1][0] - line[0][0]
    dy = line[1][1] - line[0][1]
    denominator = dx * dx + dy * dy
    t = (
        (point[0] - line[0][0]) * dx
        + (point[1] - line[0][1]) * dy
    ) / denominator
    return line[0][0] + t * dx, line[0][1] + t * dy


def _body_vector_measure(member_line: Segment, waler_axis: Segment) -> tuple[float, float]:
    endpoint = min(
        member_line,
        key=lambda point: math.dist(point, _project_to_infinite_line(point, waler_axis)),
    )
    body_point = member_line[1] if endpoint == member_line[0] else member_line[0]
    intersection = _project_to_infinite_line(endpoint, waler_axis)
    vector = body_point[0] - intersection[0], body_point[1] - intersection[1]
    normal = _axis_normal(waler_axis)
    return math.hypot(*vector), abs(vector[0] * normal[0] + vector[1] * normal[1])


def _ordered_segment(segment: Segment) -> Segment:
    return segment if segment[0] <= segment[1] else (segment[1], segment[0])


def _canonical_segments(segments: tuple[Segment, ...]) -> tuple[Segment, ...]:
    return tuple(sorted({_ordered_segment(segment) for segment in segments}))


def _rectangle(x0: float, x1: float, y0: float, y1: float) -> tuple[Segment, ...]:
    points = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    return tuple(zip(points, points[1:] + points[:1]))


@dataclass(frozen=True)
class _EnvelopeCorpusCase:
    name: str
    component_scopes: tuple[tuple[Segment, ...], ...]
    expected_kind: str

    @property
    def raw_segments(self) -> tuple[Segment, ...]:
        return tuple(segment for scope in self.component_scopes for segment in scope)


def _component_scope_corpus() -> tuple[_EnvelopeCorpusCase, ...]:
    left = _rectangle(0.0, 6000.0, 0.0, 350.0)
    right = _rectangle(6000.0, 12000.0, 0.0, 350.0)
    lower = _rectangle(0.0, 12000.0, 0.0, 350.0)
    upper = _rectangle(0.0, 12000.0, 800.0, 1150.0)
    return (
        _EnvelopeCorpusCase("touching_walers", (left, right), "separate"),
        _EnvelopeCorpusCase("parallel_components", (lower, upper), "separate"),
        _EnvelopeCorpusCase("cross_component_raw_minmax", (lower, upper), "separate"),
        _EnvelopeCorpusCase(
            "two_complete_interpretations",
            (
                _rectangle(0.0, 12000.0, 0.0, 350.0),
                _rectangle(0.0, 12000.0, 150.0, 500.0),
            ),
            "ambiguous",
        ),
    )


class WalerContactSyntheticCharacterizationTests(unittest.TestCase):
    def test_component_scope_corpus_does_not_encode_group_as_component(self):
        for case in _component_scope_corpus():
            with self.subTest(case=case.name):
                self.assertGreaterEqual(len(case.component_scopes), 2)
                self.assertIn(case.expected_kind, {"separate", "ambiguous"})
                self.assertEqual(
                    _canonical_segments(case.raw_segments),
                    _canonical_segments(tuple(reversed(case.raw_segments))),
                )
                # The flattened group deliberately has a larger transverse
                # extent than either qualified physical component.  Tests for
                # the pure extractor must therefore never use raw min/max as
                # the expected envelope.
                component_heights = [
                    max(point[1] for segment in scope for point in segment)
                    - min(point[1] for segment in scope for point in segment)
                    for scope in case.component_scopes
                ]
                raw_height = (
                    max(point[1] for segment in case.raw_segments for point in segment)
                    - min(point[1] for segment in case.raw_segments for point in segment)
                )
                if case.name != "touching_walers":
                    self.assertGreaterEqual(raw_height, max(component_heights))

    def test_side_evidence_boundary_corpus_is_explicit(self):
        tolerance = GeometryTolerances().endpoint_tolerance_mm
        cases = {
            "perpendicular": ((0.0, 0.0), (0.0, 1000.0)),
            "parallel": ((0.0, 0.0), (1000.0, 0.0)),
            "long_just_above_endpoint_tolerance": (
                (0.0, 0.0),
                (10000.0, tolerance + 1.0),
            ),
            "short_just_below_endpoint_tolerance": (
                (0.0, 0.0),
                (100.0, tolerance - 1.0),
            ),
        }
        normal = (0.0, 1.0)
        measured = {
            name: (
                math.dist(*line),
                abs(
                    (line[1][0] - line[0][0]) * normal[0]
                    + (line[1][1] - line[0][1]) * normal[1]
                ),
            )
            for name, line in cases.items()
        }

        self.assertEqual(measured["perpendicular"], (1000.0, 1000.0))
        self.assertEqual(measured["parallel"], (1000.0, 0.0))
        self.assertGreater(
            measured["long_just_above_endpoint_tolerance"][1],
            tolerance,
        )
        self.assertLess(
            measured["short_just_below_endpoint_tolerance"][1],
            tolerance,
        )

    def test_equivalent_fixture_permutations_have_one_canonical_geometry(self):
        outline = _rectangle(0.0, 12000.0, 0.0, 350.0)
        duplicate = outline[0]
        permutations = (
            outline,
            tuple(reversed(outline)),
            tuple((end, start) for start, end in outline),
            (outline[2], outline[0], outline[3], outline[1]),
            (*outline, duplicate, (duplicate[1], duplicate[0])),
        )
        expected = _canonical_segments(outline)
        for segments in permutations:
            with self.subTest(segments=segments):
                self.assertEqual(_canonical_segments(segments), expected)

    def test_no_side_and_opposite_side_fixtures_are_distinct(self):
        self.assertEqual(tuple(), tuple())
        opposite_side_vectors = ((0.0, -1000.0), (0.0, 1000.0))
        signs = {math.copysign(1.0, vector[1]) for vector in opposite_side_vectors}
        self.assertEqual(signs, {-1.0, 1.0})


class PureWalerEnvelopeFactsTests(unittest.TestCase):
    def setUp(self):
        self.tolerances = GeometryTolerances()

    def extract(self, segments, *, qualified_exterior_faces=None):
        return extract_waler_envelope_facts(
            segments,
            self.tolerances,
            source_handles=("ROOT",),
            component_key="waler:ROOT",
            qualified_exterior_faces=qualified_exterior_faces,
        )

    def test_supporting_line_width_ignores_longitudinal_overhang(self):
        first = ((0.0, 0.0), (1000.0, 0.0))
        second = ((100.0, 400.0), (1100.0, 400.0))

        self.assertGreater(_line_separation(first, second), 400.0)
        self.assertAlmostEqual(
            _supporting_line_separation(first, second),
            400.0,
        )

    def test_supporting_line_width_is_rotation_direction_and_order_invariant(self):
        first = ((0.0, 0.0), (1000.0, 0.0))
        second = ((100.0, 400.0), (1100.0, 400.0))
        angle = math.radians(37.0)

        def rotate(point: Point) -> Point:
            return (
                point[0] * math.cos(angle) - point[1] * math.sin(angle),
                point[0] * math.sin(angle) + point[1] * math.cos(angle),
            )

        rotated_first = tuple(rotate(point) for point in first)
        rotated_second = tuple(rotate(point) for point in second)
        variants = (
            (first, second),
            (second, first),
            (tuple(reversed(first)), second),
            (first, tuple(reversed(second))),
            (rotated_first, rotated_second),
            (tuple(reversed(rotated_second)), tuple(reversed(rotated_first))),
        )

        for left, right in variants:
            with self.subTest(left=left, right=right):
                self.assertAlmostEqual(
                    _supporting_line_separation(left, right),
                    400.0,
                    places=9,
                )

    def test_slightly_nonparallel_width_uses_symmetric_supporting_lines(self):
        first = ((0.0, 0.0), (1000.0, 0.0))
        second = ((100.0, 400.0), (1100.0, 410.0))
        expected = (
            _line_distance((500.0, 0.0), *second)
            + _line_distance((600.0, 405.0), *first)
        ) / 2.0

        self.assertLessEqual(
            math.degrees(math.atan2(10.0, 1000.0)),
            self.tolerances.parallel_angle_tolerance_deg,
        )
        self.assertAlmostEqual(
            _supporting_line_separation(first, second),
            expected,
        )
        self.assertAlmostEqual(
            _supporting_line_separation(second, first),
            expected,
        )

    def test_four_rail_contour_retains_outer_physical_faces(self):
        outer = _rectangle(0.0, 12000.0, 0.0, 350.0)
        internal = (
            ((0.0, 19.0), (12000.0, 19.0)),
            ((0.0, 331.0), (12000.0, 331.0)),
        )

        outcome = self.extract((*outer, *internal, internal[0], internal[1]))

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertEqual(len(outcome.facts), 1)
        fact = outcome.facts[0]
        self.assertEqual(
            tuple(round(face[0][1]) for face in fact.outer_faces),
            (0, 350),
        )
        self.assertAlmostEqual(fact.source_width, 350.0)
        self.assertEqual(fact.provisional_axis, ((0.0, 175.0), (12000.0, 175.0)))

    def test_short_local_pair_inside_full_outline_does_not_shrink_envelope(self):
        outline = _rectangle(0.0, 12000.0, 0.0, 350.0)
        local = _rectangle(4500.0, 6500.0, 100.0, 250.0)

        outcome = self.extract((*outline, *local))

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertEqual(len(outcome.facts), 1)
        self.assertAlmostEqual(outcome.facts[0].source_width, 350.0)
        self.assertEqual(outcome.facts[0].provisional_axis[0][0], 0.0)
        self.assertEqual(outcome.facts[0].provisional_axis[1][0], 12000.0)

    def test_touching_and_parallel_components_remain_separate(self):
        for case in _component_scope_corpus()[:3]:
            with self.subTest(case=case.name):
                outcome = self.extract(case.raw_segments)
                self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
                self.assertEqual(len(outcome.facts), 2)
                self.assertTrue(
                    all(math.isclose(fact.source_width, 350.0) for fact in outcome.facts)
                )

    def test_overlapping_complete_interpretations_are_ambiguous(self):
        case = _component_scope_corpus()[3]

        outcome = self.extract(case.raw_segments)

        self.assertIs(outcome.status, WalerEnvelopeStatus.AMBIGUOUS)
        self.assertEqual(outcome.code, "WALER_ENVELOPE_AMBIGUOUS")

    def test_cross_component_raw_minmax_is_not_an_envelope(self):
        lower, upper = _component_scope_corpus()[2].component_scopes

        outcome = self.extract((*lower, *upper))

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertEqual(
            sorted(round(fact.source_width) for fact in outcome.facts),
            [350, 350],
        )
        self.assertNotIn(1150, [round(fact.source_width) for fact in outcome.facts])

    def test_unconnected_parallel_rails_are_not_a_qualified_component(self):
        outcome = self.extract(
            (
                ((0.0, 0.0), (12000.0, 0.0)),
                ((0.0, 350.0), (12000.0, 350.0)),
            )
        )

        self.assertIs(outcome.status, WalerEnvelopeStatus.UNRESOLVED)
        self.assertEqual(outcome.code, "WALER_ENVELOPE_UNRESOLVED")

    def test_recognized_component_pair_can_expand_to_nearby_outer_rails(self):
        rails = (
            ((0.0, 0.0), (12000.0, 0.0)),
            ((0.0, 19.0), (12000.0, 19.0)),
            ((0.0, 331.0), (12000.0, 331.0)),
            ((0.0, 350.0), (12000.0, 350.0)),
        )

        outcome = extract_waler_envelope_facts(
            rails,
            self.tolerances,
            source_handles=("ROOT",),
            component_key="waler:ROOT",
            recognized_component_faces=(rails[1], rails[2]),
        )

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertEqual(outcome.facts[0].outer_faces, (rails[0], rails[3]))
        self.assertEqual(
            outcome.facts[0].provenance_kind,
            "recognized_component_envelope",
        )

    def test_recognized_pair_cannot_absorb_a_second_component(self):
        first = (
            ((0.0, 0.0), (12000.0, 0.0)),
            ((0.0, 350.0), (12000.0, 350.0)),
        )
        second = (
            ((0.0, 800.0), (12000.0, 800.0)),
            ((0.0, 1150.0), (12000.0, 1150.0)),
        )

        outcome = extract_waler_envelope_facts(
            (*first, *second),
            self.tolerances,
            source_handles=("ROOT",),
            component_key="waler:ROOT",
            recognized_component_faces=first,
        )

        self.assertIs(outcome.status, WalerEnvelopeStatus.UNRESOLVED)

    def test_single_line_keeps_single_contact_line_contract(self):
        line = ((0.0, 0.0), (12000.0, 0.0))

        outcome = self.extract((line,))

        self.assertIs(outcome.status, WalerEnvelopeStatus.SINGLE_LINE)
        self.assertEqual(outcome.facts[0].outer_faces, (line,))
        self.assertEqual(outcome.facts[0].source_width, 0.0)

    def test_qualified_hatch_exterior_bypasses_general_width_gate(self):
        faces = (
            ((0.0, 0.0), (12000.0, 0.0)),
            ((0.0, 800.0), (12000.0, 800.0)),
        )
        narrow_gate = GeometryTolerances(maximum_component_width_mm=100.0)

        outcome = extract_waler_envelope_facts(
            faces,
            narrow_gate,
            source_handles=("HATCH",),
            component_key="waler:HATCH",
            qualified_exterior_faces=faces,
            provenance_kind="hatch_exterior",
        )

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.facts[0].source_width, 800.0)
        self.assertEqual(outcome.facts[0].provenance_kind, "hatch_exterior")

    def test_equivalent_geometry_permutations_produce_equal_facts(self):
        outline = _rectangle(0.0, 12000.0, 0.0, 350.0)
        variants = (
            outline,
            tuple(reversed(outline)),
            tuple((end, start) for start, end in outline),
            (outline[2], outline[0], outline[3], outline[1]),
            (*outline, outline[0], (outline[0][1], outline[0][0])),
        )
        expected = self.extract(variants[0])

        for variant in variants[1:]:
            with self.subTest(variant=variant):
                self.assertEqual(self.extract(variant), expected)

    def test_module_does_not_import_ui_project_persistence_or_solver(self):
        module_path = PROJECT_ROOT / "dxf_import" / "waler_contact_face.py"
        source = module_path.read_text(encoding="utf-8")
        forbidden = (
            "tkinter",
            "dxf_import.dialog",
            "bracing_optimizer.application",
            "bracing_optimizer.infrastructure",
            "bracing_optimizer.algorithms",
        )
        self.assertFalse(any(name in source for name in forbidden))


class PureWalerOverlapTests(unittest.TestCase):
    def setUp(self):
        self.tolerances = GeometryTolerances()

    @staticmethod
    def fact(
        handle: str,
        start: Point,
        end: Point,
        *,
        evidence: tuple[Segment, ...] | None = None,
        outer_faces: tuple[Segment, ...] | None = None,
    ) -> WalerEnvelopeFacts:
        axis = (start, end)
        return WalerEnvelopeFacts(
            component_key=f"waler:{handle}",
            source_handles=(handle,),
            provisional_axis=axis,
            outer_faces=outer_faces if outer_faces is not None else (axis,),
            source_width=0.0,
            evidence_segments=(axis,) if evidence is None else evidence,
            provenance_kind="test_source_axis",
        )

    def test_ratio_uses_only_finite_provisional_axis_lengths(self):
        first = self.fact(
            "A",
            (0.0, 0.0),
            (100.0, 0.0),
            outer_faces=(((-1000.0, -10.0), (1000.0, -10.0)),),
        )
        second = self.fact(
            "B",
            (50.0, 0.0),
            (250.0, 0.0),
            outer_faces=(((-5000.0, 10.0), (5000.0, 10.0)),),
        )

        overlaps = find_significant_waler_overlaps(
            (first, second), self.tolerances
        )

        self.assertEqual(len(overlaps), 1)
        fact = overlaps[0]
        self.assertEqual(fact.source_identities, (("A",), ("B",)))
        self.assertAlmostEqual(fact.overlap_length, 50.0)
        self.assertEqual(fact.provisional_axis_lengths, (100.0, 200.0))
        self.assertAlmostEqual(fact.overlap_ratio, 0.50)
        self.assertEqual(fact.overlap_segment, ((50.0, 0.0), (100.0, 0.0)))

    def test_exact_fifty_percent_qualifies_but_just_below_does_not(self):
        first = self.fact("A", (0.0, 0.0), (100.0, 0.0))
        exact = self.fact("B", (50.0, 0.0), (150.0, 0.0))
        below = self.fact("B", (50.0001, 0.0), (150.0001, 0.0))

        self.assertEqual(
            len(find_significant_waler_overlaps((first, exact), self.tolerances)),
            1,
        )
        self.assertEqual(
            find_significant_waler_overlaps((first, below), self.tolerances),
            (),
        )

    def test_endpoint_only_and_zero_length_axes_do_not_create_facts(self):
        first = self.fact("A", (0.0, 0.0), (100.0, 0.0))
        endpoint = self.fact("B", (100.0, 0.0), (200.0, 0.0))
        zero = self.fact("B", (50.0, 0.0), (50.0, 0.0))

        self.assertEqual(
            find_significant_waler_overlaps((first, endpoint), self.tolerances),
            (),
        )
        self.assertEqual(
            find_significant_waler_overlaps((first, zero), self.tolerances),
            (),
        )

    def test_unreliable_axis_is_not_reconstructed_from_other_geometry(self):
        first = self.fact("A", (0.0, 0.0), (100.0, 0.0))
        unsupported = self.fact(
            "B",
            (0.0, 0.0),
            (100.0, 0.0),
            evidence=(),
            outer_faces=(((-1000.0, 0.0), (1000.0, 0.0)),),
        )
        nonfinite = self.fact("C", (math.nan, 0.0), (100.0, 0.0))

        self.assertEqual(
            find_significant_waler_overlaps(
                (first, unsupported, nonfinite), self.tolerances
            ),
            (),
        )

    def test_axis_and_input_order_produce_equal_overlap_fact(self):
        first = self.fact("A", (0.0, 0.0), (100.0, 0.0))
        second = self.fact("B", (25.0, 0.0), (125.0, 0.0))
        reversed_first = replace(
            first,
            provisional_axis=tuple(reversed(first.provisional_axis)),
        )
        reversed_second = replace(
            second,
            provisional_axis=tuple(reversed(second.provisional_axis)),
        )

        forward = find_significant_waler_overlaps(
            (first, second), self.tolerances
        )
        reverse = find_significant_waler_overlaps(
            (reversed_second, reversed_first), self.tolerances
        )

        self.assertEqual(forward, reverse)

    def test_unrelated_unresolved_does_not_upgrade_overlap_warning(self):
        overlap = find_significant_waler_overlaps(
            (
                self.fact("A", (0.0, 0.0), (100.0, 0.0)),
                self.fact("B", (0.0, 0.0), (100.0, 0.0)),
            ),
            self.tolerances,
        )
        unrelated = WalerContactIssue(
            "WALER_CONTACT_FACE_UNRESOLVED",
            "unrelated",
            ("A",),
        )

        self.assertEqual(
            find_waler_overlap_competitions(overlap, (), (unrelated,)),
            (),
        )

    def test_a_b_overlap_is_not_upgraded_by_a_c_competition(self):
        overlap = find_significant_waler_overlaps(
            (
                self.fact("A", (0.0, 0.0), (100.0, 0.0)),
                self.fact("B", (0.0, 0.0), (100.0, 0.0)),
            ),
            self.tolerances,
        )
        issue = TerminalTopologyIssue(
            "error",
            "AMBIGUOUS_WALER_CONNECTION",
            "A competes with C",
            "strut",
            ("S",),
            (("A",), ("C",)),
            "start",
        )

        self.assertEqual(
            find_waler_overlap_competitions(overlap, (issue,)),
            (),
        )

    def test_same_terminal_directly_upgrades_a_b_and_order_is_irrelevant(self):
        first = self.fact("A", (0.0, 0.0), (100.0, 0.0))
        second = self.fact("B", (0.0, 0.0), (100.0, 0.0))
        forward_overlap = find_significant_waler_overlaps(
            (first, second), self.tolerances
        )
        reverse_overlap = find_significant_waler_overlaps(
            (second, first), self.tolerances
        )
        forward_issue = TerminalTopologyIssue(
            "error",
            "AMBIGUOUS_WALER_CONNECTION",
            "A competes with B",
            "strut",
            ("S",),
            (("A",), ("B",)),
            "start",
        )
        reverse_issue = replace(
            forward_issue,
            competing_waler_source_handles=(("B",), ("A",)),
        )

        forward = find_waler_overlap_competitions(
            forward_overlap, (forward_issue,)
        )
        reverse = find_waler_overlap_competitions(
            reverse_overlap, (reverse_issue,)
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward), 1)
        self.assertEqual(forward[0].context_kind, "terminal")
        self.assertEqual(forward[0].context_identity, "start")
        self.assertEqual(forward[0].member_source_handles, ("S",))

    def test_same_contact_finalization_can_directly_upgrade_a_b(self):
        overlap = find_significant_waler_overlaps(
            (
                self.fact("A", (0.0, 0.0), (100.0, 0.0)),
                self.fact("B", (0.0, 0.0), (100.0, 0.0)),
            ),
            self.tolerances,
        )
        issue = WalerContactIssue(
            "WALER_CONTACT_FACE_AMBIGUOUS",
            "A and B compete in one finalization",
            ("A", "B"),
            ("S",),
            (("B",), ("A",)),
            "contact-face:S:start",
        )

        competitions = find_waler_overlap_competitions(
            overlap,
            (),
            (issue,),
        )

        self.assertEqual(len(competitions), 1)
        self.assertEqual(
            competitions[0].context_kind,
            "contact_face_finalization",
        )
        self.assertEqual(
            competitions[0].context_identity,
            "contact-face:S:start",
        )
        self.assertEqual(competitions[0].member_source_handles, ("S",))


class PureWalerTerminalAndContactTests(unittest.TestCase):
    def setUp(self):
        self.tolerances = GeometryTolerances()

    def waler(self, handle="W", y0=0.0, y1=350.0, x0=0.0, x1=12000.0):
        outcome = extract_waler_envelope_facts(
            _rectangle(x0, x1, y0, y1),
            self.tolerances,
            source_handles=(handle,),
            component_key=f"waler:{handle}",
        )
        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        return outcome.facts[0]

    def test_contextual_strut_keeps_selected_waler_source_identities(self):
        lower = self.waler("LOW", y0=0.0, y1=350.0)
        upper = self.waler("UP", y0=10000.0, y1=10350.0)
        member = MemberGeometryFacts(
            "strut",
            ("S",),
            ((6000.0, -1000.0), (6000.0, 11350.0)),
            (("LOW",), ("UP",)),
        )

        outcome = build_member_terminal_evidence(
            (member,),
            (upper, lower),
            self.tolerances,
        )

        self.assertEqual(outcome.issues, ())
        self.assertEqual(
            {item.waler_source_handles for item in outcome.evidence},
            {("LOW",), ("UP",)},
        )
        self.assertTrue(
            all(item.relation_kind == "selected_source_identity" for item in outcome.evidence)
        )
        self.assertEqual(outcome.unique_evidence, outcome.evidence)
        self.assertTrue(
            all(
                item.identity_state is TerminalIdentityState.UNIQUE
                for item in outcome.evidence
            )
        )
        with self.assertRaises(FrozenInstanceError):
            outcome.evidence[0].identity_state = TerminalIdentityState.COMPETING

    def test_normal_strut_uses_direct_relation_and_never_axis_extension(self):
        waler = self.waler()
        direct = MemberGeometryFacts(
            "strut",
            ("DIRECT",),
            ((6000.0, 100.0), (6000.0, 4000.0)),
        )
        gap = MemberGeometryFacts(
            "strut",
            ("GAP",),
            ((8000.0, 800.0), (8000.0, 4000.0)),
        )

        outcome = build_member_terminal_evidence(
            (direct, gap),
            (waler,),
            self.tolerances,
        )

        self.assertEqual(
            {(item.member_source_handles, item.relation_kind) for item in outcome.evidence},
            {(('DIRECT',), "direct")},
        )

    def test_brace_keeps_250_direct_and_600_outward_extension_boundaries(self):
        waler = self.waler(x0=-1000.0, x1=1000.0)
        direct = MemberGeometryFacts(
            "brace",
            ("DIRECT",),
            ((0.0, 600.0), (0.0, 1600.0)),
        )
        extension = MemberGeometryFacts(
            "brace",
            ("EXT",),
            ((0.0, 950.0), (0.0, 1950.0)),
        )
        too_far = MemberGeometryFacts(
            "brace",
            ("FAR",),
            ((0.0, 951.0), (0.0, 1951.0)),
        )

        outcome = build_member_terminal_evidence(
            (direct, extension, too_far),
            (waler,),
            self.tolerances,
        )

        kinds = {
            item.member_source_handles: item.relation_kind
            for item in outcome.evidence
        }
        self.assertEqual(kinds[("DIRECT",)], "direct")
        self.assertEqual(kinds[("EXT",)], "axis_extension")
        self.assertNotIn(("FAR",), kinds)

    def test_brace_extension_eligibility_uses_the_physical_envelope(self):
        waler = self.waler("W", y0=0.0, y1=350.0)
        member = MemberGeometryFacts(
            "brace",
            ("B",),
            ((6000.0, 950.0), (6000.0, 1950.0)),
        )

        outcome = build_member_terminal_evidence(
            (member,),
            (waler,),
            self.tolerances,
        )

        self.assertEqual(len(outcome.evidence), 1)
        self.assertEqual(outcome.evidence[0].relation_kind, "axis_extension")
        self.assertEqual(outcome.evidence[0].waler_source_handles, ("W",))
        self.assertEqual(outcome.evidence[0].provisional_intersection, (6000.0, 175.0))

    def test_close_competing_waler_envelopes_are_blocking_ambiguity(self):
        first = self.waler("A", y0=0.0, y1=350.0)
        second = self.waler("B", y0=20.0, y1=370.0)
        farther = self.waler("C", y0=400.0, y1=750.0)
        member = MemberGeometryFacts(
            "strut",
            ("S",),
            ((6000.0, 170.0), (6000.0, 4000.0)),
        )

        outcome = build_member_terminal_evidence(
            (member,),
            (farther, first, second),
            self.tolerances,
        )

        self.assertEqual(len(outcome.evidence), 2)
        self.assertEqual(outcome.unique_evidence, ())
        self.assertEqual(
            {
                (item.waler_source_handles, item.identity_state)
                for item in outcome.evidence
            },
            {
                (("A",), TerminalIdentityState.COMPETING),
                (("B",), TerminalIdentityState.COMPETING),
            },
        )
        self.assertEqual(outcome.issues[0].code, "AMBIGUOUS_WALER_CONNECTION")
        self.assertEqual(outcome.issues[0].severity, "error")
        self.assertEqual(outcome.issues[0].terminal_name, "start")
        self.assertEqual(outcome.issues[0].source_handles, ("S",))
        self.assertEqual(
            set(outcome.issues[0].competing_waler_source_handles),
            {("A",), ("B",)},
        )
        self.assertEqual(
            {
                item.waler_source_handles
                for item in outcome.evidence
                if item.terminal_name == outcome.issues[0].terminal_name
            },
            set(outcome.issues[0].competing_waler_source_handles),
        )
        reversed_outcome = build_member_terminal_evidence(
            (replace(member, axis=tuple(reversed(member.axis))),),
            (second, first),
            self.tolerances,
        )
        self.assertEqual(reversed_outcome.issues[0].source_handles, ("S",))
        self.assertEqual(reversed_outcome.issues[0].terminal_name, "start")
        self.assertEqual(
            reversed_outcome.issues[0].code,
            outcome.issues[0].code,
        )
        self.assertEqual(
            set(reversed_outcome.issues[0].competing_waler_source_handles),
            set(outcome.issues[0].competing_waler_source_handles),
        )

    def test_axis_extension_ambiguity_keeps_only_eligible_competing_relations(self):
        nearest = self.waler("A", y0=0.0, y1=350.0)
        close = self.waler("B", y0=10.0, y1=360.0)
        beyond_extension = self.waler("C", y0=-100.0, y1=250.0)
        member = MemberGeometryFacts(
            "brace",
            ("BRACE",),
            ((6000.0, 950.0), (6000.0, 1950.0)),
        )

        outcome = build_member_terminal_evidence(
            (member,),
            (beyond_extension, close, nearest),
            self.tolerances,
        )

        issue = outcome.issues[0]
        self.assertEqual(issue.code, "AMBIGUOUS_BRACE_AXIS_WALER_CONNECTION")
        self.assertEqual(issue.terminal_name, "start")
        self.assertEqual(
            issue.competing_waler_source_handles,
            (("B",), ("A",)),
        )
        self.assertEqual(
            {
                (item.waler_source_handles, item.relation_kind, item.identity_state)
                for item in outcome.evidence
            },
            {
                (("A",), "axis_extension", TerminalIdentityState.COMPETING),
                (("B",), "axis_extension", TerminalIdentityState.COMPETING),
            },
        )

    def test_brace_direct_terminal_characterization_covers_zero_one_and_two_identities(self):
        first = self.waler("A", y0=0.0, y1=350.0)
        second = self.waler("B", y0=20.0, y1=370.0)
        cases = (
            ((), 0, 0),
            ((first,), 1, 0),
            ((first, second), 2, 1),
        )
        member = MemberGeometryFacts(
            "brace",
            ("BRACE",),
            ((6000.0, 170.0), (6000.0, 4000.0)),
        )

        for walers, evidence_count, issue_count in cases:
            with self.subTest(walers=len(walers)):
                outcome = build_member_terminal_evidence(
                    (member,), walers, self.tolerances
                )
                self.assertEqual(len(outcome.evidence), evidence_count)
                self.assertEqual(len(outcome.issues), issue_count)
                if issue_count:
                    issue = outcome.issues[0]
                    self.assertEqual(issue.terminal_name, "start")
                    self.assertEqual(
                        set(issue.competing_waler_source_handles),
                        {("A",), ("B",)},
                    )

    def test_unique_terminal_evidence_drives_contact_face_before_unresolved_brace_verdict(self):
        lower = self.waler("W16", y0=0.0, y1=350.0)
        upper_a = self.waler("W18", y0=10000.0, y1=10350.0)
        upper_b = self.waler("W19", y0=10020.0, y1=10370.0)
        member = MemberGeometryFacts(
            "brace",
            ("B15",),
            ((6000.0, 350.0), (6000.0, 10020.0)),
        )

        topology = build_member_terminal_evidence(
            (member,), (lower, upper_a, upper_b), self.tolerances
        )
        contact = resolve_waler_contact_faces(
            (lower, upper_a, upper_b), topology.evidence, self.tolerances
        )
        verdict = build_brace_terminal_verdicts(
            (member,), topology, contact, self.tolerances
        )[0]
        reversed_topology = build_member_terminal_evidence(
            (member,), (upper_b, upper_a, lower), self.tolerances
        )
        reversed_contact = resolve_waler_contact_faces(
            (upper_b, upper_a, lower),
            reversed_topology.evidence,
            self.tolerances,
        )
        reversed_verdict = build_brace_terminal_verdicts(
            (member,), reversed_topology, reversed_contact, self.tolerances
        )[0]

        self.assertEqual(
            [
                (item.terminal_name, item.waler_source_handles, item.identity_state)
                for item in topology.evidence
            ],
            [
                ("start", ("W16",), TerminalIdentityState.UNIQUE),
                ("end", ("W18",), TerminalIdentityState.COMPETING),
                ("end", ("W19",), TerminalIdentityState.COMPETING),
            ],
        )
        issue = topology.issues[0]
        self.assertEqual(issue.terminal_name, "end")
        self.assertEqual(
            set(issue.competing_waler_source_handles),
            {("W18",), ("W19",)},
        )
        self.assertEqual(
            {item.source_handles for item in contact.resolutions},
            {("W16",), ("W18",), ("W19",)},
        )
        self.assertEqual(contact.issues, ())
        self.assertIs(verdict.status, BraceTerminalStatus.UNRESOLVED)
        self.assertIsNone(verdict.formal_axis)
        self.assertEqual(verdict.terminal_source_handles, ())
        self.assertEqual(reversed_topology, topology)
        self.assertEqual(reversed_contact, contact)
        self.assertEqual(reversed_verdict, verdict)

    def test_brace_verdict_requires_two_distinct_final_faces_and_valid_intersections(self):
        member = MemberGeometryFacts(
            "brace",
            ("B",),
            ((500.0, 0.0), (500.0, 2000.0)),
        )
        evidence = (
            MemberTerminalEvidence(
                "brace", ("B",), "start", ("LOW",), (500.0, 0.0),
                (500.0, 2000.0), "direct",
            ),
            MemberTerminalEvidence(
                "brace", ("B",), "end", ("UP",), (500.0, 2000.0),
                (500.0, 0.0), "direct",
            ),
        )
        topology = TerminalTopologyOutcome(evidence=evidence)
        resolved_contact = WalerContactOutcome(
            resolutions=(
                WalerContactResolution(
                    ("LOW",), ((0.0, 0.0), (1000.0, 0.0)),
                    ((0.0, 0.0), (1000.0, 0.0)), 1,
                ),
                WalerContactResolution(
                    ("UP",), ((0.0, 2000.0), (1000.0, 2000.0)),
                    ((0.0, 2000.0), (1000.0, 2000.0)), -1,
                ),
            )
        )

        resolved = build_brace_terminal_verdicts(
            (member,), topology, resolved_contact, self.tolerances
        )[0]
        provisional = build_brace_terminal_verdicts(
            (member,), topology,
            WalerContactOutcome(resolutions=resolved_contact.resolutions[:1]),
            self.tolerances,
        )[0]
        no_intersection = build_brace_terminal_verdicts(
            (member,), topology,
            WalerContactOutcome(
                resolutions=(
                    resolved_contact.resolutions[0],
                    replace(
                        resolved_contact.resolutions[1],
                        selected_face=((2000.0, 2000.0), (3000.0, 2000.0)),
                    ),
                )
            ),
            self.tolerances,
        )[0]
        same_waler = build_brace_terminal_verdicts(
            (member,),
            TerminalTopologyOutcome(
                evidence=(evidence[0], replace(evidence[1], waler_source_handles=("LOW",)))
            ),
            WalerContactOutcome(resolutions=resolved_contact.resolutions[:1]),
            self.tolerances,
        )[0]
        short_member = replace(member, axis=((500.0, 0.0), (500.0, 50.0)))
        short_topology = TerminalTopologyOutcome(
            evidence=(
                evidence[0],
                replace(
                    evidence[1],
                    provisional_intersection=(500.0, 50.0),
                    body_point=(500.0, 0.0),
                ),
            )
        )
        short_contact = WalerContactOutcome(
            resolutions=(
                resolved_contact.resolutions[0],
                replace(
                    resolved_contact.resolutions[1],
                    selected_face=((0.0, 50.0), (1000.0, 50.0)),
                ),
            )
        )
        invalid_length = build_brace_terminal_verdicts(
            (short_member,), short_topology, short_contact, self.tolerances
        )[0]

        self.assertIs(resolved.status, BraceTerminalStatus.RESOLVED)
        self.assertEqual(
            resolved.formal_axis,
            ((500.0, 0.0), (500.0, 2000.0)),
        )
        self.assertIs(provisional.status, BraceTerminalStatus.UNRESOLVED)
        self.assertIn("WALER_CONTACT_FACE_UNRESOLVED", provisional.reason_codes)
        self.assertIs(no_intersection.status, BraceTerminalStatus.UNRESOLVED)
        self.assertIn("WALER_CONTACT_FINALIZE_FAILED", no_intersection.reason_codes)
        self.assertIs(same_waler.status, BraceTerminalStatus.UNRESOLVED)
        self.assertIn("BRACE_SAME_WALER_CONNECTION", same_waler.reason_codes)
        self.assertIs(invalid_length.status, BraceTerminalStatus.UNRESOLVED)
        self.assertIn("WALER_CONTACT_FINALIZE_FAILED", invalid_length.reason_codes)

    def test_numerically_equal_direct_relations_are_blocking_ambiguity(self):
        first = self.waler("A", y0=0.0, y1=350.0)
        shifted = WalerEnvelopeFacts(
            component_key="waler:B",
            source_handles=("B",),
            provisional_axis=(
                (first.provisional_axis[0][0], first.provisional_axis[0][1] + 1e-10),
                (first.provisional_axis[1][0], first.provisional_axis[1][1] + 1e-10),
            ),
            outer_faces=tuple(
                (
                    (line[0][0], line[0][1] + 1e-10),
                    (line[1][0], line[1][1] + 1e-10),
                )
                for line in first.outer_faces
            ),
            source_width=first.source_width,
            evidence_segments=first.evidence_segments,
        )
        member = MemberGeometryFacts(
            "strut",
            ("S",),
            ((6000.0, 350.0), (6000.0, 4000.0)),
        )

        forward = build_member_terminal_evidence(
            (member,), (shifted, first), self.tolerances
        )
        reverse = build_member_terminal_evidence(
            (member,), (first, shifted), self.tolerances
        )

        self.assertEqual(forward, reverse)
        self.assertEqual(len(forward.evidence), 2)
        self.assertEqual(forward.unique_evidence, ())
        self.assertTrue(
            all(
                item.identity_state is TerminalIdentityState.COMPETING
                for item in forward.evidence
            )
        )
        self.assertEqual(forward.issues[0].severity, "error")
        self.assertEqual(forward.issues[0].code, "AMBIGUOUS_WALER_CONNECTION")
        self.assertEqual(
            set(forward.issues[0].competing_waler_source_handles),
            {("A",), ("B",)},
        )

    def test_support_side_selects_outermost_face_not_internal_rail(self):
        outcome = extract_waler_envelope_facts(
            (
                *_rectangle(-39000.0, 39000.0, 8450.0, 8800.0),
                ((-39000.0, 8469.0), (39000.0, 8469.0)),
                ((-39000.0, 8781.0), (39000.0, 8781.0)),
            ),
            self.tolerances,
            source_handles=("C86",),
            component_key="waler:C86",
        )
        fact = outcome.facts[0]
        evidence = MemberTerminalEvidence(
            "strut",
            ("D17",),
            "end",
            ("C86",),
            (-15498.5, 8625.0),
            (-15498.5, -23550.0),
            "selected_source_identity",
        )

        resolved = resolve_waler_contact_faces(
            (fact,),
            (evidence,),
            self.tolerances,
        )

        self.assertEqual(resolved.issues, ())
        self.assertEqual(
            tuple(round(point[1]) for point in resolved.resolutions[0].selected_face),
            (8450, 8450),
        )

    def test_opposite_side_selects_opposite_outer_face(self):
        waler = self.waler()
        evidence = MemberTerminalEvidence(
            "strut",
            ("UPPER",),
            "start",
            ("W",),
            (6000.0, 175.0),
            (6000.0, 5000.0),
            "direct",
        )

        outcome = resolve_waler_contact_faces((waler,), (evidence,), self.tolerances)

        self.assertEqual(outcome.issues, ())
        self.assertEqual(
            tuple(point[1] for point in outcome.resolutions[0].selected_face),
            (350.0, 350.0),
        )

    def test_no_side_opposite_side_and_degenerate_evidence_fail_closed(self):
        waler = self.waler()
        lower = MemberTerminalEvidence(
            "strut", ("LOW",), "end", ("W",), (6000.0, 175.0), (6000.0, -1000.0), "direct"
        )
        upper = MemberTerminalEvidence(
            "brace", ("UP",), "start", ("W",), (7000.0, 175.0), (7000.0, 1000.0), "direct"
        )
        degenerate = MemberTerminalEvidence(
            "strut", ("FLAT",), "start", ("W",), (1000.0, 175.0), (5000.0, 175.0), "direct"
        )

        no_evidence = resolve_waler_contact_faces((waler,), (), self.tolerances)
        conflict = resolve_waler_contact_faces((waler,), (lower, upper), self.tolerances)
        flat = resolve_waler_contact_faces((waler,), (degenerate,), self.tolerances)

        self.assertEqual(no_evidence.issues[0].code, "WALER_CONTACT_FACE_UNRESOLVED")
        self.assertEqual(conflict.issues[0].code, "WALER_CONTACT_FACE_AMBIGUOUS")
        self.assertEqual(flat.issues[0].code, "WALER_CONTACT_FACE_UNRESOLVED")
        self.assertEqual(no_evidence.resolutions, ())
        self.assertEqual(conflict.resolutions, ())
        self.assertEqual(flat.resolutions, ())

    def test_unique_first_side_authority_and_competing_fallback(self):
        waler = self.waler()

        def evidence(handle, normal_component, state):
            return MemberTerminalEvidence(
                "strut",
                (handle,),
                "start",
                ("W",),
                (6000.0, 175.0),
                (6000.0, 175.0 + normal_component),
                "direct",
                state,
            )

        unique_above = evidence(
            "UNIQUE_ABOVE", 1000.0, TerminalIdentityState.UNIQUE
        )
        competing_below = evidence(
            "COMPETING_BELOW", -1000.0, TerminalIdentityState.COMPETING
        )
        competing_above = evidence(
            "COMPETING_ABOVE", 1200.0, TerminalIdentityState.COMPETING
        )

        unique_first = resolve_waler_contact_faces(
            (waler,), (competing_below, unique_above), self.tolerances
        )
        reversed_unique_first = resolve_waler_contact_faces(
            (waler,), (unique_above, competing_below), self.tolerances
        )
        same_side_fallback = resolve_waler_contact_faces(
            (waler,), (competing_above,), self.tolerances
        )
        conflicting_fallback = resolve_waler_contact_faces(
            (waler,), (competing_above, competing_below), self.tolerances
        )

        self.assertEqual(len(unique_first.resolutions), 1)
        self.assertEqual(reversed_unique_first, unique_first)
        self.assertEqual(unique_first.resolutions[0].side_sign, 1)
        self.assertEqual(
            unique_first.resolutions[0].supporting_evidence,
            (unique_above,),
        )
        warning = unique_first.issues[0]
        self.assertEqual(
            warning.code, "WALER_COMPETING_SIDE_EVIDENCE_IGNORED"
        )
        self.assertEqual(warning.severity, "warning")
        self.assertEqual(warning.unique_member_source_handles, ("UNIQUE_ABOVE",))
        self.assertEqual(
            warning.ignored_competing_member_source_handles,
            ("COMPETING_BELOW",),
        )
        self.assertEqual(len(same_side_fallback.resolutions), 1)
        self.assertEqual(same_side_fallback.issues, ())
        self.assertEqual(conflicting_fallback.resolutions, ())
        self.assertEqual(
            conflicting_fallback.issues[0].code,
            "WALER_CONTACT_FACE_AMBIGUOUS",
        )

    def test_endpoint_tolerance_characterization_is_the_named_side_boundary(self):
        waler = self.waler()
        threshold = self.tolerances.endpoint_tolerance_mm

        def evidence(handle, normal_component):
            return MemberTerminalEvidence(
                "strut",
                (handle,),
                "start",
                ("W",),
                (6000.0, 175.0),
                (16000.0, 175.0 + normal_component),
                "direct",
            )

        below = resolve_waler_contact_faces(
            (waler,),
            (evidence("BELOW", threshold - 1.0),),
            self.tolerances,
        )
        above = resolve_waler_contact_faces(
            (waler,),
            (evidence("ABOVE", threshold + 1.0),),
            self.tolerances,
        )

        self.assertEqual(below.issues[0].code, "WALER_CONTACT_FACE_UNRESOLVED")
        self.assertEqual(above.issues, ())
        self.assertEqual(len(above.resolutions), 1)

    def test_member_and_waler_direction_reversal_are_deterministic(self):
        waler = self.waler()
        member = MemberGeometryFacts(
            "strut",
            ("S",),
            ((6000.0, -1000.0), (6000.0, 5000.0)),
        )
        reverse_member = MemberGeometryFacts(
            "strut",
            ("S",),
            tuple(reversed(member.axis)),
        )
        reverse_waler = type(waler)(
            component_key=waler.component_key,
            source_handles=waler.source_handles,
            provisional_axis=tuple(reversed(waler.provisional_axis)),
            outer_faces=tuple(tuple(reversed(face)) for face in reversed(waler.outer_faces)),
            source_width=waler.source_width,
            evidence_segments=waler.evidence_segments,
            provenance_kind=waler.provenance_kind,
        )

        forward_topology = build_member_terminal_evidence(
            (member,), (waler,), self.tolerances
        )
        reverse_topology = build_member_terminal_evidence(
            (reverse_member,), (reverse_waler,), self.tolerances
        )
        forward = resolve_waler_contact_faces(
            (waler,), forward_topology.evidence, self.tolerances
        )
        reverse = resolve_waler_contact_faces(
            (reverse_waler,), reverse_topology.evidence, self.tolerances
        )

        self.assertEqual(
            {resolution.selected_face for resolution in forward.resolutions},
            {resolution.selected_face for resolution in reverse.resolutions},
        )


class WalerContactStagingTests(unittest.TestCase):
    @staticmethod
    def _candidate(
        role: str,
        handle: str,
        axis: Segment,
        *,
        envelope: WalerEnvelopeFacts | None = None,
    ) -> _Candidate:
        return _Candidate(
            start=axis[0],
            end=axis[1],
            recognition_method=(
                "parallel_edges_midline" if role == "waler" else "existing_centerline"
            ),
            centerline_computed=role == "waler",
            source_width=envelope.source_width if envelope is not None else 0.0,
            confidence=0.95,
            layer=role.upper(),
            handles={handle},
            entity_types={"LWPOLYLINE" if role == "waler" else "LINE"},
            block_instances=[],
            source_keys={f"{role}:{handle}"},
            warnings=[],
            boundary_lines=envelope.outer_faces if envelope is not None else (),
            recognized_axis=axis,
            waler_envelope_facts=(envelope,) if envelope is not None else (),
        )

    def test_apply_exception_does_not_partially_mutate_live_candidates(self):
        tolerances = GeometryTolerances()
        outcome = extract_waler_envelope_facts(
            _rectangle(0.0, 12000.0, 0.0, 350.0),
            tolerances,
            source_handles=("W",),
            component_key="waler:W",
        )
        fact = outcome.facts[0]
        candidate = _Candidate(
            start=fact.provisional_axis[0],
            end=fact.provisional_axis[1],
            recognition_method="parallel_edges_midline",
            centerline_computed=True,
            source_width=fact.source_width,
            confidence=0.95,
            layer="WALER",
            handles={"W"},
            entity_types={"LWPOLYLINE"},
            block_instances=[],
            source_keys={"waler:W"},
            warnings=[],
            boundary_lines=fact.outer_faces,
            recognized_axis=fact.provisional_axis,
            waler_envelope_facts=(fact,),
        )
        candidates = {"waler": [candidate]}
        original_geometry = (candidate.start, candidate.end, candidate.recognition_method)

        def fail_after_staged_mutation(staged, *_args):
            staged["waler"][0].start = (999.0, 999.0)
            raise RuntimeError("synthetic staged apply failure")

        with patch(
            "dxf_import.recognition._apply_terminal_resolutions",
            side_effect=fail_after_staged_mutation,
        ):
            messages = _resolve_waler_contact_geometry(candidates, tolerances)

        self.assertEqual(
            (
                candidates["waler"][0].start,
                candidates["waler"][0].end,
                candidates["waler"][0].recognition_method,
            ),
            original_geometry,
        )
        self.assertIn(
            "WALER_CONTACT_FINALIZE_FAILED",
            {message.code for message in messages},
        )
        self.assertEqual(
            candidates["waler"][0].waler_contact_face_state,
            "provisional",
        )

    def test_staged_unique_first_warning_is_traceable_and_non_blocking(self):
        tolerances = GeometryTolerances()
        first = extract_waler_envelope_facts(
            _rectangle(0.0, 12000.0, 0.0, 350.0),
            tolerances,
            source_handles=("A",),
            component_key="waler:A",
        ).facts[0]
        second = replace(first, component_key="waler:B", source_handles=("B",))
        unique = self._candidate(
            "strut", "UNIQUE", ((6000.0, 175.0), (6000.0, 4000.0))
        )
        unique.selected_waler_source_handles = (("A",),)
        competing = self._candidate(
            "strut", "COMPETING", ((6000.0, -4000.0), (6000.0, 175.0))
        )
        staged = {
            "waler": [
                self._candidate("waler", "A", first.provisional_axis, envelope=first),
                self._candidate("waler", "B", second.provisional_axis, envelope=second),
            ],
            "strut": [competing, unique],
            "brace": [],
            "corner_brace": [],
        }

        messages = _resolve_waler_contact_geometry(staged, tolerances)

        warning = next(
            message
            for message in messages
            if message.code == "WALER_COMPETING_SIDE_EVIDENCE_IGNORED"
        )
        states = {
            next(iter(candidate.handles)): candidate.waler_contact_face_state
            for candidate in staged["waler"]
        }
        members = {
            next(iter(candidate.handles)): candidate
            for candidate in staged["strut"]
        }
        self.assertEqual(warning.severity, "warning")
        self.assertEqual(set(warning.source_handles), {"A", "UNIQUE", "COMPETING"})
        self.assertIn("unique 構件來源：UNIQUE", warning.message)
        self.assertIn("competing 構件來源：COMPETING", warning.message)
        self.assertEqual(states, {"A": "formal", "B": "formal"})
        self.assertFalse(members["UNIQUE"].waler_terminal_blocked)
        self.assertTrue(members["COMPETING"].waler_terminal_blocked)

    def test_overlap_messages_require_direct_same_terminal_provenance(self):
        tolerances = GeometryTolerances()
        first = extract_waler_envelope_facts(
            _rectangle(0.0, 12000.0, 0.0, 350.0),
            tolerances,
            source_handles=("A",),
            component_key="waler:A",
        ).facts[0]
        second = replace(
            first,
            component_key="waler:B",
            source_handles=("B",),
        )

        def resolve(*, with_terminal: bool, reverse: bool = False):
            walers = [
                self._candidate("waler", "A", first.provisional_axis, envelope=first),
                self._candidate("waler", "B", second.provisional_axis, envelope=second),
            ]
            if reverse:
                walers.reverse()
            staged = {
                "waler": walers,
                "strut": (
                    [
                        self._candidate(
                            "strut",
                            "S",
                            ((6000.0, 175.0), (6000.0, 4000.0)),
                        )
                    ]
                    if with_terminal
                    else []
                ),
                "brace": [],
                "corner_brace": [],
            }
            messages = _resolve_waler_contact_geometry(staged, tolerances)
            diagnostics = tuple(
                sorted(
                    (
                        message.severity,
                        message.code,
                        message.source_handles,
                        message.message,
                    )
                    for message in messages
                    if message.code
                    in {
                        "WALER_SOURCE_OVERLAP",
                        "WALER_OVERLAP_COMPETITION",
                    }
                )
            )
            states = {
                next(iter(candidate.handles)): candidate.waler_contact_face_state
                for candidate in staged["waler"]
            }
            return diagnostics, states, messages

        warning_only, unresolved_states, warning_messages = resolve(
            with_terminal=False
        )
        blocking, blocked_states, _blocking_messages = resolve(with_terminal=True)
        reversed_blocking, reversed_states, _reversed_messages = resolve(
            with_terminal=True,
            reverse=True,
        )
        overlap_warning = next(
            message
            for message in warning_messages
            if message.code == "WALER_SOURCE_OVERLAP"
        )
        warning_result = DXFImportResult(
            source_path="synthetic-overlap.dxf",
            layer_names=("WALER",),
            selected_layers={"waler": ("WALER",)},
            layer_info=(),
            walers=(),
            struts=(),
            braces=(),
            entity_debug=(),
            messages=(overlap_warning,),
            source_entity_counts={},
        )

        self.assertEqual(
            [(severity, code) for severity, code, *_rest in warning_only],
            [("warning", "WALER_SOURCE_OVERLAP")],
        )
        self.assertEqual(unresolved_states, {"A": "provisional", "B": "provisional"})
        self.assertTrue(warning_result.can_import)
        self.assertEqual(build_problem_records(warning_result)[0].severity, "warning")
        self.assertEqual(
            {(severity, code) for severity, code, *_rest in blocking},
            {
                ("warning", "WALER_SOURCE_OVERLAP"),
                ("error", "WALER_OVERLAP_COMPETITION"),
            },
        )
        competition = next(
            item for item in blocking if item[1] == "WALER_OVERLAP_COMPETITION"
        )
        self.assertEqual(set(competition[2]), {"A", "B", "S"})
        self.assertIn("terminal start", competition[3])
        self.assertEqual(blocked_states, {"A": "formal", "B": "formal"})
        self.assertEqual(blocking, reversed_blocking)
        self.assertEqual(blocked_states, reversed_states)

    def test_staging_preserves_structured_strut_terminal_ambiguity(self):
        tolerances = GeometryTolerances()
        first = extract_waler_envelope_facts(
            _rectangle(0.0, 12000.0, 0.0, 350.0),
            tolerances,
            source_handles=("A",),
            component_key="waler:A",
        ).facts[0]
        second = extract_waler_envelope_facts(
            _rectangle(0.0, 12000.0, 20.0, 370.0),
            tolerances,
            source_handles=("B",),
            component_key="waler:B",
        ).facts[0]
        strut = self._candidate(
            "strut",
            "S",
            ((6000.0, 170.0), (6000.0, 4000.0)),
        )
        staged = {
            "waler": [
                self._candidate(
                    "waler", "A", first.provisional_axis, envelope=first
                ),
                self._candidate(
                    "waler", "B", second.provisional_axis, envelope=second
                ),
            ],
            "strut": [strut],
            "brace": [],
            "corner_brace": [],
        }

        _resolve_waler_contact_geometry(staged, tolerances)

        issue = staged["strut"][0].waler_terminal_topology[0]
        self.assertEqual(issue.terminal_name, "start")
        self.assertEqual(issue.reason_code, "AMBIGUOUS_WALER_CONNECTION")
        self.assertEqual(
            set(issue.competing_waler_source_handles),
            {("A",), ("B",)},
        )

    def test_member_and_waler_collection_order_preserve_final_outcome(self):
        tolerances = GeometryTolerances()
        first = extract_waler_envelope_facts(
            _rectangle(0.0, 6000.0, 0.0, 350.0),
            tolerances,
            source_handles=("WA",),
            component_key="waler:WA",
        ).facts[0]
        second = extract_waler_envelope_facts(
            _rectangle(6000.0, 12000.0, 3000.0, 3350.0),
            tolerances,
            source_handles=("WB",),
            component_key="waler:WB",
        ).facts[0]
        walers = (
            self._candidate("waler", "WA", first.provisional_axis, envelope=first),
            self._candidate("waler", "WB", second.provisional_axis, envelope=second),
        )
        struts = (
            self._candidate("strut", "SA", ((3000.0, 350.0), (3000.0, 2000.0))),
            self._candidate("strut", "SB", ((9000.0, 3350.0), (9000.0, 5000.0))),
        )

        def resolve(waler_order, strut_order):
            staged = {
                "waler": list(waler_order),
                "strut": list(strut_order),
                "brace": [],
                "corner_brace": [],
            }
            messages = _resolve_waler_contact_geometry(staged, tolerances)
            geometry = {
                (role, next(iter(candidate.handles))): (
                    candidate.start,
                    candidate.end,
                    candidate.waler_terminal_source_handles,
                    candidate.waler_terminal_topology,
                    candidate.waler_contact_face_state,
                )
                for role in ("waler", "strut")
                for candidate in staged[role]
            }
            diagnostics = tuple(
                sorted(
                    (message.severity, message.code, message.source_handles)
                    for message in messages
                )
            )
            return geometry, diagnostics

        forward = resolve(walers, struts)
        reverse = resolve(tuple(reversed(walers)), tuple(reversed(struts)))

        self.assertEqual(forward, reverse)
        self.assertTrue(forward[0][("strut", "SA")][3][0].waler_source_handles)
        self.assertEqual(forward[0][("waler", "WA")][-1], "formal")
        self.assertEqual(forward[0][("waler", "WB")][-1], "formal")


@unittest.skipUnless(
    Y05_DXF_PATH.is_file()
    and Y29_DXF_PATH.is_file()
    and Y1A_DXF_PATH.is_file(),
    "Y05/Y29/Y1A DXF test assets unavailable",
)
class WalerWidthFixtureCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = {}
        fixtures = (
            ("Y05", Y05_DXF_PATH, Y05_LAYER_MAPPING),
            ("Y29", Y29_DXF_PATH, Y29_LAYER_MAPPING),
            ("Y1A", Y1A_DXF_PATH, Y1A_LAYER_MAPPING),
        )
        for name, path, mapping in fixtures:
            importer = DXFImporter(path).read()
            cls.results[name] = importer.convert(
                layer_roles=_internal_layer_roles(importer, mapping),
                material_specs=WALER_MATERIAL_SPECS,
            )

    def test_all_fixture_walers_match_characterized_width_material_and_gate(self):
        changed_over_geometry_tolerance = []
        material_changes = []
        gate_changes = []

        for fixture, expected_rows in WALER_WIDTH_CHARACTERIZATION.items():
            result = self.results[fixture]
            actual_by_handle = {
                waler.source_handles[0]: waler
                for waler in result.walers
                if len(waler.source_handles) == 1
            }
            self.assertEqual(set(actual_by_handle), set(expected_rows))
            for handle, row in expected_rows.items():
                legacy_width, new_width, legacy_material, new_material, gate_applies = row
                waler = actual_by_handle[handle]
                with self.subTest(fixture=fixture, handle=handle):
                    self.assertAlmostEqual(
                        waler.source_width,
                        new_width,
                        delta=1e-5,
                    )
                    self.assertEqual(waler.material_spec, new_material)
                    if new_material == "RC":
                        self.assertEqual(waler.material_spec_source, "auto_hatch")
                    else:
                        self.assertEqual(
                            recognize_material_spec_from_width(
                                legacy_width,
                                "圍令",
                                WALER_MATERIAL_SPECS,
                            ),
                            legacy_material,
                        )
                        self.assertEqual(
                            recognize_material_spec_from_width(
                                new_width,
                                "圍令",
                                WALER_MATERIAL_SPECS,
                            ),
                            new_material,
                        )
                    if abs(new_width - legacy_width) > 50.0:
                        changed_over_geometry_tolerance.append((fixture, handle))
                    if legacy_material != new_material:
                        material_changes.append(
                            (fixture, handle, legacy_material, new_material)
                        )
                    if gate_applies and (legacy_width <= 600.0) != (new_width <= 600.0):
                        gate_changes.append((fixture, handle))

        self.assertEqual(changed_over_geometry_tolerance, [])
        self.assertEqual(
            material_changes,
            [("Y29", "69F", "H414x405", "H400x400")],
        )
        self.assertEqual(gate_changes, [])


@unittest.skipUnless(Y29_DXF_PATH.is_file(), "Y29 DXF test asset unavailable")
class Y29WalerOverlapRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y29_DXF_PATH).read()
        cls.layer_roles = _internal_layer_roles(cls.importer, Y29_LAYER_MAPPING)
        cls.result = cls.importer.convert(
            layer_roles=cls.layer_roles,
            material_specs=WALER_MATERIAL_SPECS,
        )
        cls.without_69c = cls.importer.convert(
            layer_roles=cls.layer_roles,
            excluded_sources=(ExcludedSource("waler", ("69C",)),),
        )
        cls.without_721 = cls.importer.convert(
            layer_roles=cls.layer_roles,
            excluded_sources=(ExcludedSource("waler", ("721",)),),
        )
        cls.without_69f = cls.importer.convert(
            layer_roles=cls.layer_roles,
            excluded_sources=(ExcludedSource("waler", ("69F",)),),
        )

    @staticmethod
    def _waler_by_source(result, handle):
        return next(
            waler for waler in result.walers if handle in waler.source_handles
        )

    def test_y29_w18_and_w19_use_orthogonal_width_for_material_matching(self):
        w18 = self._waler_by_source(self.result, "69F")
        w19 = self._waler_by_source(self.result, "720")

        self.assertEqual((w18.id, w19.id), ("W18", "W19"))
        self.assertAlmostEqual(w18.source_width, 400.000099, delta=1e-5)
        self.assertAlmostEqual(w19.source_width, 400.0, delta=1e-5)
        self.assertEqual(w18.source_handles, ("69F",))
        self.assertEqual(w18.contact_face_state, "formal")
        self.assertEqual(w18.material_spec, "H400x400")
        self.assertEqual(w19.material_spec, "H400x400")
        self.assertEqual(w18.material_spec_source, "auto_width")
        self.assertEqual(w19.material_spec_source, "auto_width")

    def test_y29_w18_w19_overlap_and_b15_ambiguity_survive_width_correction(self):
        overlap_codes = {
            message.code
            for message in self.result.messages
            if {"69F", "720"}.issubset(message.source_handles)
        }
        brace = next(
            member for member in self.result.braces if "71E" in member.source_handles
        )
        ambiguity = next(
            message
            for message in self.result.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
            and "71E" in message.source_handles
        )

        self.assertTrue(
            {"WALER_SOURCE_OVERLAP", "WALER_OVERLAP_COMPETITION"}.issubset(
                overlap_codes
            )
        )
        self.assertTrue({"71E", "69F", "720"}.issubset(ambiguity.source_handles))
        self.assertEqual((brace.from_waler, brace.to_waler), ("", ""))
        self.assertFalse(brace.has_formal_connection)
        self.assertEqual(brace.recommended_start_point_id, "")
        self.assertEqual(brace.recommended_end_point_id, "")
        self.assertEqual(brace.selected_start_point_id, "")
        self.assertEqual(brace.selected_end_point_id, "")

    def test_y29_terminal_competition_characterization_uses_source_identity(self):
        """Freeze the real fixture mapping before changing relation semantics."""

        waler_ids = {
            handle: self._waler_by_source(self.result, handle).id
            for handle in ("69C", "69F", "720", "721")
        }
        s19 = next(
            member for member in self.result.struts if "48B" in member.source_handles
        )
        s19_ambiguities = {
            item.terminal_name: item.competing_waler_source_handles
            for item in s19.terminal_topology
            if item.reason_code == "AMBIGUOUS_WALER_CONNECTION"
        }
        b15_ambiguity = next(
            message
            for message in self.result.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
            and "71E" in message.source_handles
        )
        s19_messages = tuple(
            message
            for message in self.result.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
            and "48B" in message.source_handles
        )

        self.assertEqual(
            waler_ids,
            {"69C": "W17", "69F": "W18", "720": "W19", "721": "W20"},
        )
        self.assertEqual(
            s19_ambiguities,
            {
                "end": (("69C",), ("721",)),
                "start": (("69F",), ("720",)),
            },
        )
        self.assertIn("terminal end (direct)", b15_ambiguity.message)
        self.assertEqual(len(s19_messages), 2)
        self.assertTrue(
            any("terminal start (direct)" in message.message for message in s19_messages)
        )
        self.assertTrue(
            any("terminal end (direct)" in message.message for message in s19_messages)
        )
        self.assertTrue(
            {"71E", "69F", "720"}.issubset(b15_ambiguity.source_handles)
        )
        self.assertFalse(
            any(
                {("69C",), ("69F",)}.issubset(
                    set(item.competing_waler_source_handles)
                )
                for item in s19.terminal_topology
            )
        )

    def test_w17_w20_overlap_is_warning_plus_direct_blocking_competition(self):
        codes = {
            message.code
            for message in self.result.messages
            if {"69C", "721"}.issubset(set(message.source_handles))
        }
        walers = {
            handle: self._waler_by_source(self.result, handle)
            for handle in ("69C", "721")
        }

        self.assertIn("WALER_SOURCE_OVERLAP", codes)
        self.assertIn("WALER_OVERLAP_COMPETITION", codes)
        self.assertIn("AMBIGUOUS_WALER_CONNECTION", codes)
        self.assertEqual(
            {waler.contact_face_state for waler in walers.values()},
            {"formal"},
        )
        self.assertTrue(
            all(
                math.isclose(waler.world_start[1], -422610.0001598086)
                and math.isclose(waler.world_end[1], -422610.0001598086)
                for waler in walers.values()
            )
        )
        self.assertFalse(self.result.can_import)

    def test_excluding_either_source_rebuilds_remaining_formal_outer_face(self):
        cases = (
            (self.without_69c, "721", "69C"),
            (self.without_721, "69C", "721"),
        )
        for result, remaining, excluded in cases:
            with self.subTest(excluded=excluded):
                waler = self._waler_by_source(result, remaining)
                related_messages = tuple(
                    message
                    for message in result.messages
                    if {"69C", "721"} & set(message.source_handles)
                )
                self.assertEqual(waler.contact_face_state, "formal")
                self.assertAlmostEqual(waler.world_start[1], -422610.0001598086)
                self.assertAlmostEqual(waler.world_end[1], -422610.0001598086)
                self.assertFalse(
                    {
                        "WALER_SOURCE_OVERLAP",
                        "WALER_OVERLAP_COMPETITION",
                        "WALER_CONTACT_FACE_UNRESOLVED",
                    }
                    & {message.code for message in related_messages}
                )

    def test_contact_face_state_is_review_only_and_project_row_is_unchanged(self):
        competing_side_formal = self._waler_by_source(self.result, "69C")
        formal = self._waler_by_source(self.without_721, "69C")
        expected_keys = {
            "WalerID",
            "StartX",
            "StartY",
            "EndX",
            "EndY",
            "material_spec",
            "Remark",
        }

        self.assertEqual(set(competing_side_formal.to_project_row()), expected_keys)
        self.assertEqual(set(formal.to_project_row()), expected_keys)
        self.assertNotIn("contact_face_state", competing_side_formal.to_project_row())

    def test_debug_snapshot_serializes_state_and_legacy_waler_defaults_safely(self):
        waler = self._waler_by_source(self.result, "69C")
        debug_row = next(
            row
            for row in self.result.to_debug_dict()["converted"]["walers"]
            if "69C" in row["source_handles"]
        )
        legacy_row = dict(debug_row)
        legacy_row.pop("contact_face_state")
        legacy_row.pop("engineering_line_authority")
        legacy_row.pop("source_width_state")

        restored = type(waler)(**legacy_row)

        self.assertEqual(debug_row["contact_face_state"], "formal")
        self.assertEqual(debug_row["engineering_line_authority"], "automatic")
        self.assertIn(
            debug_row["source_width_state"],
            {"unique", "unknown", "ambiguous"},
        )
        self.assertEqual(restored.contact_face_state, "formal")
        self.assertEqual(restored.engineering_line_authority, "automatic")
        self.assertEqual(
            restored.source_width_state,
            "unique" if restored.source_width > 0.0 else "unknown",
        )
        self.assertTrue(restored.has_formal_contact_face)

    def test_source_width_state_uses_all_orthogonal_measurements(self):
        def fact(key, width):
            return WalerEnvelopeFacts(
                key,
                (key,),
                ((0.0, 0.0), (100.0, 0.0)),
                (
                    ((0.0, -width / 2.0), (100.0, -width / 2.0)),
                    ((0.0, width / 2.0), (100.0, width / 2.0)),
                ),
                width,
                (),
            )

        tolerances = GeometryTolerances(material_width_tolerance_mm=1.0)

        self.assertEqual(
            _waler_source_width_assessment((), tolerances),
            ("unknown", 0.0),
        )
        self.assertEqual(
            _waler_source_width_assessment((fact("A", 400.0),), tolerances),
            ("unique", 400.0),
        )
        self.assertEqual(
            _waler_source_width_assessment(
                (fact("A", 400.0), fact("B", 400.5)),
                tolerances,
            ),
            ("unique", 400.0),
        )
        self.assertEqual(
            _waler_source_width_assessment(
                (fact("A", 350.0), fact("B", 400.0)),
                tolerances,
            ),
            ("ambiguous", 0.0),
        )

        existing = self._waler_by_source(self.result, "69C")
        ambiguous_auto = replace(
            existing,
            source_width=400.0,
            source_width_state="ambiguous",
            material_spec="H400x400",
            material_spec_source="auto_width",
        )
        manual = replace(
            ambiguous_auto,
            material_spec="MANUAL",
            material_spec_source="manual",
        )
        auto_result = recognize_result_material_specs(
            replace(self.result, walers=(ambiguous_auto,)),
            WALER_MATERIAL_SPECS,
        )
        manual_result = recognize_result_material_specs(
            replace(self.result, walers=(manual,)),
            WALER_MATERIAL_SPECS,
        )
        self.assertEqual(
            (auto_result.walers[0].material_spec, auto_result.walers[0].material_spec_source),
            ("", ""),
        )
        self.assertEqual(
            (manual_result.walers[0].material_spec, manual_result.walers[0].material_spec_source),
            ("MANUAL", "manual"),
        )

    def test_review_projection_localizes_pair_and_affected_terminal_sources(self):
        records = build_problem_records(self.result)
        items = build_review_items(self.result, records)
        warning = next(
            record
            for record in records
            if record.code == "WALER_SOURCE_OVERLAP"
            and {"69C", "721"}.issubset(set(record.source_handles))
        )
        competition = next(
            record
            for record in records
            if record.code == "WALER_OVERLAP_COMPETITION"
            and {"69C", "721"}.issubset(set(record.source_handles))
        )
        waler_items = {
            item.member_id: item
            for item in items
            if item.member_id in {"W17", "W20"}
        }

        self.assertEqual(warning.severity, "warning")
        self.assertTrue({"69C", "721"}.issubset(set(warning.source_handles)))
        self.assertTrue({"W17", "W20"}.issubset(set(warning.member_ids)))
        self.assertEqual(competition.severity, "error")
        self.assertTrue({"69C", "721"}.issubset(set(competition.source_handles)))
        self.assertGreater(len(competition.source_handles), 2)
        self.assertIn("構件端點", competition.description)
        self.assertNotIn("terminal", competition.description)
        self.assertNotIn("建議排除", competition.description)
        self.assertEqual(set(waler_items), {"W17", "W20"})
        self.assertTrue(
            all(
                self._waler_by_source(self.result, handle).contact_face_state
                == "formal"
                for handle in ("69C", "721")
            )
        )
        self.assertFalse(
            next(
                brace
                for brace in self.result.braces
                if "71E" in brace.source_handles
            ).has_formal_connection
        )
        self.assertFalse(self.result.can_import)
        self.assertTrue(
            all(
                {
                    "WALER_SOURCE_OVERLAP",
                    "WALER_OVERLAP_COMPETITION",
                }.issubset({problem.code for problem in item.problems})
                for item in waler_items.values()
            )
        )

    def test_y29_w6_w12_problem_descriptions_use_review_list_identifiers(self):
        records = build_problem_records(self.result)
        messages = tuple(
            message
            for message in self.result.messages
            if message.code
            in {"WALER_SOURCE_OVERLAP", "WALER_OVERLAP_COMPETITION"}
            and {"232", "4E4"}.issubset(set(message.source_handles))
        )
        projected = tuple(
            record
            for record in records
            if record.code
            in {"WALER_SOURCE_OVERLAP", "WALER_OVERLAP_COMPETITION"}
            and {"232", "4E4"}.issubset(set(record.source_handles))
        )

        self.assertTrue(messages)
        self.assertEqual(len(projected), len(messages))
        self.assertTrue(
            all("W6（232）" in record.description for record in projected)
        )
        self.assertTrue(
            all("W12（4E4）" in record.description for record in projected)
        )
        self.assertCountEqual(
            [(record.severity, record.code, record.source_handles) for record in projected],
            [(message.severity, message.code, message.source_handles) for message in messages],
        )
        self.assertFalse(self.result.can_import)

    def test_b15_duplicate_terminal_is_blocking_and_has_no_formal_endpoint_choice(self):
        brace = next(
            member for member in self.result.braces if "71E" in member.source_handles
        )
        ambiguity = next(
            message
            for message in self.result.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
            and "71E" in message.source_handles
        )

        self.assertEqual((brace.from_waler, brace.to_waler), ("", ""))
        self.assertFalse(brace.has_formal_connection)
        self.assertEqual(brace.recommended_start_point_id, "")
        self.assertEqual(brace.recommended_end_point_id, "")
        self.assertEqual(brace.selected_start_point_id, "")
        self.assertEqual(brace.selected_end_point_id, "")
        self.assertFalse(
            any(
                point.recommended_for
                or point.point_type
                in {"waler_intersection", "extended_axis_waler_intersection"}
                for point in brace.candidate_points
            )
        )
        project_rows = replace(self.result, messages=()).to_project_rows()
        self.assertEqual(
            len(project_rows["braces"]),
            sum(member.has_formal_connection for member in self.result.braces),
        )
        self.assertTrue({"71E", "69F", "720"}.issubset(ambiguity.source_handles))
        self.assertIn("terminal end", ambiguity.message)
        self.assertIn("69F", ambiguity.message)
        self.assertIn("720", ambiguity.message)
        problem = next(
            record
            for record in build_problem_records(self.result)
            if record.code == "AMBIGUOUS_WALER_CONNECTION"
            and "71E" in record.source_handles
        )
        self.assertEqual(problem.member_ids, (brace.id,))
        for handle in ("69F", "720"):
            waler = self._waler_by_source(self.result, handle)
            self.assertIn(f"{waler.id}（{handle}）", problem.description)

    def test_b15_unique_w19_uses_axis_to_formal_face_intersection(self):
        unresolved = next(
            member for member in self.result.braces if "71E" in member.source_handles
        )
        resolved = next(
            member
            for member in self.without_69f.braces
            if "71E" in member.source_handles
        )
        w19 = self._waler_by_source(self.without_69f, "720")
        expected = _line_segment_intersection_point(
            (unresolved.world_start, unresolved.world_end),
            (w19.world_start, w19.world_end),
            self.importer.tolerances.endpoint_tolerance_mm,
        )
        source_endpoints = tuple(
            line.world_end
            for line in unresolved.line_candidates
            if line.source == "recognized_boundary"
        )
        fixture_p07 = (
            sum(point[0] for point in source_endpoints) / len(source_endpoints),
            sum(point[1] for point in source_endpoints) / len(source_endpoints),
        )
        self.assertIsNotNone(expected)
        resolved_endpoint = (
            resolved.world_start
            if math.dist(resolved.world_start, expected) <= math.dist(resolved.world_end, expected)
            else resolved.world_end
        )

        self.assertEqual(len(source_endpoints), 2)
        self.assertTrue(resolved.has_formal_connection)
        self.assertIn(w19.id, {resolved.from_waler, resolved.to_waler})
        self.assertLessEqual(
            math.dist(resolved_endpoint, expected),
            self.importer.tolerances.endpoint_tolerance_mm,
        )
        self.assertLessEqual(
            math.dist(resolved_endpoint, fixture_p07),
            self.importer.tolerances.endpoint_tolerance_mm,
        )

    def test_production_import_never_calls_legacy_brace_nearest_fallback(self):
        with patch(
            "dxf_import.candidate_points.resolve_brace_waler_connection",
            side_effect=AssertionError("production Brace fallback must not run"),
        ):
            result = self.importer.convert(layer_roles=self.layer_roles)

        brace = next(
            member for member in result.braces if "71E" in member.source_handles
        )
        self.assertFalse(brace.has_formal_connection)
        self.assertTrue(
            any(
                message.code == "AMBIGUOUS_WALER_CONNECTION"
                and "71E" in message.source_handles
                for message in result.messages
            )
        )


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF test asset unavailable")
class Y05WalerContactCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y05_DXF_PATH).read()
        cls.layer_roles = _internal_layer_roles(cls.importer, Y05_LAYER_MAPPING)
        cls.waler_groups = {
            group.root_handle: group
            for group in _candidate_groups(cls.importer, cls.layer_roles, "waler")
        }
        cls.result = cls.importer.convert(layer_roles=cls.layer_roles)

    def test_c86_preserves_four_longitudinal_rail_levels_before_pair_collapse(self):
        group = self.waler_groups["C86"]
        rail_levels = sorted(
            {
                round(start[1])
                for primitive in group.primitives
                for start, end in primitive.segments()
                if abs(start[1] - end[1]) < 1e-6
                and math.dist(start, end) > 1000.0
            }
        )
        candidate, messages = _candidate_from_group(
            group,
            "waler",
            self.importer.tolerances,
        )

        self.assertEqual(rail_levels, [8450, 8469, 8781, 8800])
        self.assertEqual(messages, [])
        self.assertIsNotNone(candidate)
        self.assertAlmostEqual(candidate.start[1], 8625.0, places=3)
        self.assertEqual(
            sorted(round(line[0][1]) for line in candidate.boundary_lines),
            [8469, 8781],
        )

    def test_c86_pure_envelope_uses_its_outer_rails(self):
        group = self.waler_groups["C86"]
        segments = tuple(
            segment
            for primitive in group.primitives
            for segment in primitive.segments()
        )

        outcome = extract_waler_envelope_facts(
            segments,
            self.importer.tolerances,
            source_handles=("C86",),
            component_key="waler:C86",
        )

        self.assertIs(outcome.status, WalerEnvelopeStatus.RECOGNIZED)
        self.assertEqual(len(outcome.facts), 1)
        self.assertEqual(
            tuple(round(face[0][1]) for face in outcome.facts[0].outer_faces),
            (8450, 8800),
        )
        self.assertAlmostEqual(outcome.facts[0].source_width, 350.0, places=3)

    def test_w7_and_w12_keep_distinct_source_identities(self):
        by_id = {waler.id: waler for waler in self.result.walers}
        self.assertEqual(by_id["W7"].source_handles, ("C86",))
        self.assertEqual(by_id["W12"].source_handles, ("C97",))
        self.assertNotEqual(by_id["W7"].source_handles, by_id["W12"].source_handles)

    def test_w7_and_contextual_struts_commit_one_shared_outer_contact_face(self):
        walers = {waler.id: waler for waler in self.result.walers}
        struts = {strut.id: strut for strut in self.result.struts}
        w7 = walers["W7"]

        self.assertEqual(w7.source_handles, ("C86",))
        self.assertEqual(w7.recognition_method, "parallel_edges_midline")
        self.assertAlmostEqual(w7.source_width, 350.0, places=3)
        self.assertAlmostEqual(w7.world_start[1], 8450.0, places=3)
        self.assertAlmostEqual(w7.world_end[1], 8450.0, places=3)
        self.assertEqual(w7.contact_face_state, "formal")
        for strut_id in ("S11", "S20"):
            with self.subTest(strut=strut_id):
                strut = struts[strut_id]
                self.assertEqual(strut.to_waler, "W7")
                self.assertAlmostEqual(strut.world_end[1], 8450.0, places=3)
                self.assertAlmostEqual(
                    math.dist(
                        strut.world_end,
                        strut.line_candidates[0].world_end,
                    ),
                    0.0,
                    places=6,
                )
                end_contacts = tuple(
                    point
                    for point in strut.candidate_points
                    if point.point_type == "waler_intersection"
                    and "end" in point.recommended_for
                )
                self.assertEqual(len(end_contacts), 1)
                self.assertAlmostEqual(
                    math.dist(end_contacts[0].world_point, strut.world_end),
                    0.0,
                    places=6,
                )
                self.assertEqual(
                    set(end_contacts[0].source_handles),
                    {"C86", strut.source_handles[0]},
                )

        ambiguous_sources = {
            handle
            for message in self.result.messages
            if message.code == "AMBIGUOUS_WALER_CONNECTION"
            for handle in message.source_handles
        }
        self.assertTrue({"C86", "C97"}.isdisjoint(ambiguous_sources))

    def test_unresolved_w12_is_reviewable_and_keeps_import_blocked(self):
        contact_message = next(
            message
            for message in self.result.messages
            if message.code == "WALER_CONTACT_FACE_UNRESOLVED"
            and "C97" in message.source_handles
        )
        problems = build_problem_records(self.result)
        review_items = build_review_items(self.result, problems)
        w12_item = next(item for item in review_items if item.member_id == "W12")

        self.assertEqual(contact_message.severity, "error")
        self.assertFalse(self.result.can_import)
        self.assertIn("C97", w12_item.source_handles)
        self.assertIn(
            "WALER_CONTACT_FACE_UNRESOLVED",
            {problem.code for problem in w12_item.problems},
        )

    def test_w7_related_struts_have_large_reliable_body_vectors(self):
        group = self.waler_groups["C86"]
        candidate, _messages = _candidate_from_group(
            group,
            "waler",
            self.importer.tolerances,
        )
        provisional_axis = (candidate.start, candidate.end)
        related = tuple(
            strut
            for strut in self.result.struts
            if "W7" in {strut.from_waler, strut.to_waler}
        )
        measurements = tuple(
            _body_vector_measure((strut.world_start, strut.world_end), provisional_axis)
            for strut in related
        )

        self.assertEqual(len(related), 15)
        self.assertTrue(
            all(
                total > 30000.0 and normal_component > 30000.0
                for total, normal_component in measurements
            )
        )


@unittest.skipUnless(Y1A_DXF_PATH.is_file(), "Y1A DXF test asset unavailable")
class Y1AWalerContactCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y1A_DXF_PATH).read()
        cls.layer_roles = _internal_layer_roles(cls.importer, Y1A_LAYER_MAPPING)
        cls.waler_groups = _candidate_groups(cls.importer, cls.layer_roles, "waler")
        cls.result = cls.importer.convert(layer_roles=cls.layer_roles)

    def test_w1_to_w4_contact_faces_are_the_existing_general_cad_baseline(self):
        expected = {
            "W1": ((338238.287, -725295.569), (338238.287, -703095.570)),
            "W2": ((338238.287, -703545.506), (433838.390, -703545.598)),
            "W3": ((338238.287, -724845.506), (433838.390, -724845.506)),
            "W4": ((433838.339, -703095.506), (433838.390, -725295.506)),
        }
        by_id = {waler.id: waler for waler in self.result.walers}
        for waler_id, expected_line in expected.items():
            with self.subTest(waler=waler_id):
                actual = (by_id[waler_id].world_start, by_id[waler_id].world_end)
                self.assertEqual(by_id[waler_id].contact_face_state, "formal")
                direct_error = sum(
                    math.dist(point, expected_point)
                    for point, expected_point in zip(actual, expected_line)
                )
                reverse_error = sum(
                    math.dist(point, expected_point)
                    for point, expected_point in zip(actual, reversed(expected_line))
                )
                aligned_expected = (
                    expected_line if direct_error <= reverse_error else tuple(reversed(expected_line))
                )
                for point, expected_point in zip(actual, aligned_expected):
                    self.assertAlmostEqual(point[0], expected_point[0], delta=0.1)
                    self.assertAlmostEqual(point[1], expected_point[1], delta=0.1)

    def test_actual_y1a_body_vectors_are_well_above_endpoint_tolerance(self):
        provisional_by_handle = {}
        for group in self.waler_groups:
            candidate, _messages = _candidate_from_group(
                group,
                "waler",
                self.importer.tolerances,
            )
            provisional_by_handle[next(iter(group.handles))] = (
                candidate.start,
                candidate.end,
            )
        formal_by_id = {waler.id: waler for waler in self.result.walers}
        measurements = []
        for strut in self.result.struts:
            for waler_id in (strut.from_waler, strut.to_waler):
                handle = formal_by_id[waler_id].source_handles[0]
                measurements.append(
                    _body_vector_measure(
                        (strut.world_start, strut.world_end),
                        provisional_by_handle[handle],
                    )
                )

        self.assertEqual(len(measurements), 30)
        self.assertGreater(
            min(normal for _total, normal in measurements),
            self.importer.tolerances.endpoint_tolerance_mm * 100.0,
        )


if __name__ == "__main__":
    unittest.main()
