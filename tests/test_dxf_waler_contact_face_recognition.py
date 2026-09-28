from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import unittest

from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter, Y05_LAYER_MAPPING, Y1A_LAYER_MAPPING
from dxf_import.models import GeometryTolerances
from dxf_import.recognition import _candidate_from_group
from dxf_import.waler_contact_face import (
    MemberGeometryFacts,
    MemberTerminalEvidence,
    WalerEnvelopeStatus,
    build_member_terminal_evidence,
    extract_waler_envelope_facts,
    resolve_waler_contact_faces,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
Y05_DXF_PATH = next(PROJECT_ROOT.glob("670-CO-Y05*.dxf"), None)
Y1A_DXF_PATH = PROJECT_ROOT / "Y1A擋土支撐簡化版.dxf"


Point = tuple[float, float]
Segment = tuple[Point, Point]


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
            ((0.0, 425.0), (0.0, 1425.0)),
        )
        extension = MemberGeometryFacts(
            "brace",
            ("EXT",),
            ((0.0, 775.0), (0.0, 1775.0)),
        )
        too_far = MemberGeometryFacts(
            "brace",
            ("FAR",),
            ((0.0, 776.0), (0.0, 1776.0)),
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

    def test_close_competing_provisional_walers_are_ambiguous(self):
        first = self.waler("A", y0=0.0, y1=350.0)
        second = self.waler("B", y0=20.0, y1=370.0)
        member = MemberGeometryFacts(
            "strut",
            ("S",),
            ((6000.0, 170.0), (6000.0, 4000.0)),
        )

        outcome = build_member_terminal_evidence(
            (member,),
            (first, second),
            self.tolerances,
        )

        self.assertEqual(len(outcome.evidence), 1)
        self.assertEqual(outcome.evidence[0].waler_source_handles, ("A",))
        self.assertEqual(outcome.issues[0].code, "AMBIGUOUS_WALER_CONNECTION")
        self.assertEqual(outcome.issues[0].severity, "warning")
        self.assertEqual(
            set(outcome.issues[0].competing_waler_source_handles),
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
                for point, expected_point in zip(actual, expected_line):
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
