from __future__ import annotations

from collections import Counter
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import ezdxf
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import (
    DXFImporter,
    Y05_LAYER_MAPPING,
    Y1A_LAYER_MAPPING,
    Y29_LAYER_MAPPING,
)
from dxf_import.models import (
    Beam,
    CoordinateSystem,
    DXFImportResult,
    ExcludedSource,
    apply_coordinate_system,
)
from dxf_import.recognition import (
    _BIMJoistRouteResult,
    _Candidate,
    _GeometryGroup,
    _Primitive,
    _route_bim_joist_block,
)
from dxf_import.validation import build_review_items
from dxf_import.joist_recognition import (
    JOIST_COLUMN_TERMINAL_WINDOW_MM,
    JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM,
    JoistColumnStationReference,
    JoistContact,
    JoistContextSnapshot,
    JoistMemberReference,
    JoistPairRelation,
    JoistPrimitive,
    JoistRecognitionInput,
    JoistRecognitionStatus,
    column_midpoint_is_eligible,
    pair_spacing_is_eligible,
    recognize_bim_joist,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
Y05_DXF_PATH = next(PROJECT_ROOT.glob("670-CO-Y05*.dxf"), None)
Y1A_DXF_PATH = PROJECT_ROOT / "Y1A擋土支撐簡化版.dxf"
Y29_DXF_PATH = PROJECT_ROOT / "Y29_test.dxf"


def _line(
    start: tuple[float, float],
    end: tuple[float, float],
    handle: str,
) -> JoistPrimitive:
    return JoistPrimitive((start, end), False, "LINE", handle)


def _source(offsets: tuple[float, ...], *, start: float = 0.0, end: float = 1000.0):
    return JoistRecognitionInput(
        root_handle="ROOT",
        root_entity_type="INSERT",
        role="beam",
        primitives=tuple(
            _line((start, offset), (end, offset), f"L{index}")
            for index, offset in enumerate(offsets)
        ),
    )


def _double_c_source(*, start: float = 0.0, end: float = 1000.0):
    return _source((0.0, 50.0, 100.0, 518.0, 568.0, 618.0), start=start, end=end)


def _terminal_residual_source(
    residual_segments: dict[int, tuple[tuple[float, float], ...]] | None = None,
) -> JoistRecognitionInput:
    offsets = (0.0, 50.0, 100.0, 518.0, 568.0, 618.0)
    if residual_segments is None:
        residual_segments = {
            **{index: ((-675.0, -175.0),) for index in range(3)},
            **{index: ((-640.0, -175.0),) for index in range(3, 6)},
        }
    primitives = [
        _line((175.0, offset), (3000.0, offset), f"MAIN{index}")
        for index, offset in enumerate(offsets)
    ]
    primitives.extend(
        _line((start, offsets[index]), (end, offsets[index]), f"R{index}_{part}")
        for index, segments in sorted(residual_segments.items())
        for part, (start, end) in enumerate(segments)
    )
    return JoistRecognitionInput(
        root_handle="ROOT",
        root_entity_type="INSERT",
        role="beam",
        primitives=tuple(primitives),
    )


def _terminal_context() -> JoistContextSnapshot:
    return JoistContextSnapshot(
        struts=(_strut("S1", 0.0, width=350.0),),
        column_stations=(_column("C1", "S1"),),
    )


def _single_c_source(*, start: float = 0.0, end: float = 1000.0):
    return _source((0.0, 20.0, 40.0, 100.0, 120.0, 140.0), start=start, end=end)


def _strut(
    identifier: str,
    x: float,
    *,
    width: float = 350.0,
) -> JoistMemberReference:
    return JoistMemberReference(
        identifier,
        (x, -100.0),
        (x, 800.0),
        (identifier,),
        width,
    )


def _column(identifier: str, strut_id: str, station: float = 409.0):
    return JoistColumnStationReference(identifier, strut_id, station)


def _recognition_source_from_group(group) -> JoistRecognitionInput:
    return JoistRecognitionInput(
        root_handle=group.root_handle or "",
        root_entity_type=group.root_entity_type,
        role=group.role,
        primitives=tuple(
            JoistPrimitive(
                tuple(primitive.points),
                primitive.closed,
                primitive.entity_type,
                primitive.source_handle,
                primitive.source_width,
            )
            for primitive in group.primitives
        ),
    )


class JoistEngineeringBoundaryTests(unittest.TestCase):
    def test_pair_spacing_uses_inclusive_513_to_523_contract(self):
        for spacing in (513.0, 518.0, 523.0):
            with self.subTest(spacing=spacing):
                self.assertTrue(pair_spacing_is_eligible(spacing))
        for spacing in (512.999, 523.001):
            with self.subTest(spacing=spacing):
                self.assertFalse(pair_spacing_is_eligible(spacing))

    def test_column_midpoint_uses_inclusive_plus_or_minus_two_contract(self):
        for column_station in (407.0, 409.0, 411.0):
            with self.subTest(column_station=column_station):
                self.assertTrue(
                    column_midpoint_is_eligible(150.0, 668.0, column_station)
                )
        for column_station in (406.999, 411.001):
            with self.subTest(column_station=column_station):
                self.assertFalse(
                    column_midpoint_is_eligible(150.0, 668.0, column_station)
                )


class BIMJoistRecognitionTests(unittest.TestCase):
    def test_terminal_recovery_ambiguity_routes_as_runtime_critical_diagnostic(self):
        source = _terminal_residual_source(
            {
                index: ((-675.0, -175.0), (-500.0, -175.0))
                for index in range(6)
            }
        )
        group = _GeometryGroup(
            "beam:ROOT",
            "beam",
            "BEAM",
            [
                _Primitive(
                    list(item.points),
                    item.closed,
                    item.entity_type,
                    item.source_handle,
                )
                for item in source.primitives
            ],
            {"ROOT"},
            {"LINE", "INSERT"},
            [],
            "ROOT",
            "INSERT",
        )

        routed = _route_bim_joist_block(
            group,
            DXFImporter("unused.dxf").tolerances,
            _terminal_context(),
        )

        self.assertTrue(routed.handled)
        self.assertEqual((), routed.candidates)
        self.assertEqual("critical", routed.messages[0].severity)
        self.assertEqual(
            "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
            routed.messages[0].code,
        )

    def test_ambiguous_bim_root_stays_unresolved_and_never_stages_beams(self):
        primitives = [
            _Primitive(list(item.points), False, "LINE", item.source_handle)
            for item in (
                *_double_c_source().primitives,
                *tuple(
                    _line((offset, 0.0), (offset, 1000.0), f"V{index}")
                    for index, offset in enumerate(
                        (0.0, 50.0, 100.0, 518.0, 568.0, 618.0)
                    )
                ),
            )
        ]
        group = _GeometryGroup(
            "beam:AMBIGUOUS",
            "beam",
            "BEAM",
            primitives,
            {"AMBIGUOUS"},
            {"LINE", "INSERT"},
            [],
            "AMBIGUOUS",
            "INSERT",
        )

        routed = _route_bim_joist_block(
            group,
            DXFImporter("unused.dxf").tolerances,
            JoistContextSnapshot(),
        )
        result = DXFImportResult(
            source_path="ambiguous.dxf",
            layer_names=("BEAM",),
            selected_layers={"beam": ("BEAM",)},
            layer_info=(),
            walers=(),
            struts=(),
            braces=(),
            entity_debug=(),
            messages=routed.messages,
            source_entity_counts={"beam": 1},
        )
        items = build_review_items(result)

        self.assertTrue(routed.handled)
        self.assertEqual((), routed.candidates)
        self.assertEqual("critical", routed.messages[0].severity)
        self.assertEqual(
            "BIM_JOIST_CONFLICTING_WHOLE_AXES",
            routed.messages[0].code,
        )
        self.assertEqual(1, len(items))
        self.assertEqual("unresolved", items[0].status)
        self.assertEqual("beam", items[0].role)

    def test_non_bim_beam_insert_keeps_legacy_fallback(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0.0, 0.0), (1000.0, 0.0), dxfattribs={"layer": "WALER"})
        model.add_line((0.0, 1000.0), (1000.0, 1000.0), dxfattribs={"layer": "WALER"})
        model.add_line((500.0, 0.0), (500.0, 1000.0), dxfattribs={"layer": "STRUT"})
        block = document.blocks.new("LEGACY_BEAM_ROOT")
        block.add_line((100.0, 500.0), (900.0, 500.0))
        model.add_blockref(block.name, (0.0, 0.0), dxfattribs={"layer": "BEAM"})
        importer = DXFImporter("legacy-beam.dxf")
        importer._document = document
        importer._source_fingerprint = "SYNTHETIC"

        result = importer.convert(
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BEAM": "beam",
            }
        )

        self.assertEqual(1, len(result.beams))
        self.assertEqual("existing_centerline", result.beams[0].recognition_method)
        self.assertEqual("", result.beams[0].joist_assembly_key)

    def test_runtime_bm_geometry_mapping_ignores_insert_enumeration_order(self):
        def convert(order):
            document = ezdxf.new("R2010")
            for layer in ("WALER", "STRUT", "COLUMN", "BEAM"):
                document.layers.add(layer)
            model = document.modelspace()
            model.add_line((0.0, -1000.0), (3500.0, -1000.0), dxfattribs={"layer": "WALER"})
            model.add_line((0.0, 2000.0), (3500.0, 2000.0), dxfattribs={"layer": "WALER"})
            for x in (500.0, 2500.0):
                model.add_line((x, -1000.0), (x, 2000.0), dxfattribs={"layer": "STRUT"})
                model.add_line((x - 50.0, 309.0), (x + 50.0, 309.0), dxfattribs={"layer": "COLUMN"})
            for name, insertion_x in (("A", 0.0), ("B", 2000.0)):
                block = document.blocks.new(f"JOIST_{name}")
                for offset in (0.0, 50.0, 100.0, 518.0, 568.0, 618.0):
                    block.add_line((0.0, offset), (1000.0, offset))
            for name in order:
                model.add_blockref(
                    f"JOIST_{name}",
                    (0.0 if name == "A" else 2000.0, 0.0),
                    dxfattribs={"layer": "BEAM"},
                )
            importer = DXFImporter("ordered-bim-beams.dxf")
            importer._document = document
            importer._source_fingerprint = "SYNTHETIC"
            return importer.convert(
                layer_roles={
                    "WALER": "waler",
                    "STRUT": "strut",
                    "COLUMN": "column",
                    "BEAM": "beam",
                }
            )

        first = convert(("A", "B"))
        second = convert(("B", "A"))

        geometry = lambda result: tuple(
            (beam.id, beam.start, beam.end, beam.joist_axis_slot)
            for beam in result.beams
        )
        self.assertEqual(geometry(first), geometry(second))
        self.assertEqual(4, len(first.beams))

    def test_importer_builds_formal_upstream_context_before_beam_router(self):
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "COLUMN", "BEAM"):
            document.layers.add(layer)
        model = document.modelspace()
        model.add_line((0.0, 0.0), (1000.0, 0.0), dxfattribs={"layer": "WALER"})
        model.add_line((0.0, 1000.0), (1000.0, 1000.0), dxfattribs={"layer": "WALER"})
        model.add_line((500.0, 0.0), (500.0, 1000.0), dxfattribs={"layer": "STRUT"})
        model.add_line((450.0, 500.0), (550.0, 500.0), dxfattribs={"layer": "COLUMN"})
        block = document.blocks.new("BEAM_ROOT")
        block.add_line((0.0, 0.0), (1000.0, 0.0))
        model.add_blockref(block.name, (0.0, 0.0), dxfattribs={"layer": "BEAM"})
        importer = DXFImporter("stage-order.dxf")
        importer._document = document
        importer._source_fingerprint = "SYNTHETIC"
        seen_contexts = []

        def route(_group, _tolerances, context):
            seen_contexts.append(context)
            return _BIMJoistRouteResult(True)

        with patch("dxf_import.importer._route_bim_joist_block", side_effect=route):
            importer.convert(
                layer_roles={
                    "WALER": "waler",
                    "STRUT": "strut",
                    "COLUMN": "column",
                    "BEAM": "beam",
                }
            )

        self.assertEqual(2, len(seen_contexts))
        context = seen_contexts[0]
        self.assertTrue(all(item == context for item in seen_contexts))
        self.assertEqual(("S1",), tuple(item.id for item in context.struts))
        self.assertEqual(
            (("C1", "S1"),),
            tuple((item.id, item.strut_id) for item in context.column_stations),
        )

    def test_double_c_root_yields_two_envelope_centre_axes(self):
        context = JoistContextSnapshot(
            struts=(_strut("S1", 500.0),),
            column_stations=(_column("C1", "S1"),),
        )

        outcome = recognize_bim_joist(_double_c_source(), context)

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(2, len(outcome.axes))
        self.assertAlmostEqual(50.0, outcome.axes[0].start[1])
        self.assertAlmostEqual(568.0, outcome.axes[1].start[1])
        self.assertAlmostEqual(
            518.0,
            outcome.axes[1].start[1] - outcome.axes[0].start[1],
        )
        self.assertEqual({"finite_segment_intersection"}, {
            contact.recognition_method for contact in outcome.contacts
        })

    def test_column_terminal_window_uses_inclusive_outward_signed_projection(self):
        self.assertEqual(700.0, JOIST_COLUMN_TERMINAL_WINDOW_MM)
        for terminal, expected_start in (
            (0.0, 0.0),
            (-700.0, -700.0),
            (-700.001, 175.0),
        ):
            with self.subTest(terminal=terminal):
                inner_endpoint = 100.0 if terminal == 0.0 else -175.0
                segments = {
                    index: ((terminal, inner_endpoint),)
                    for index in range(6)
                }
                outcome = recognize_bim_joist(
                    _terminal_residual_source(segments),
                    _terminal_context(),
                )
                self.assertEqual(
                    JoistRecognitionStatus.RECOGNIZED_PAIR,
                    outcome.status,
                )
                self.assertEqual(
                    (expected_start, expected_start),
                    tuple(axis.start[0] for axis in outcome.axes),
                )

        reverse_side = {
            index: ((200.0, 300.0),)
            for index in range(6)
        }
        reverse_outcome = recognize_bim_joist(
            _terminal_residual_source(reverse_side),
            _terminal_context(),
        )
        self.assertEqual(
            (175.0, 175.0),
            tuple(axis.start[0] for axis in reverse_outcome.axes),
        )

    def test_terminal_recovery_requires_quorum_for_each_sibling(self):
        missing_second_quorum = {
            0: ((-675.0, -175.0),),
            1: ((-675.0, -175.0),),
            3: ((-640.0, -175.0),),
        }

        outcome = recognize_bim_joist(
            _terminal_residual_source(missing_second_quorum),
            _terminal_context(),
        )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(
            (175.0, 175.0),
            tuple(axis.start[0] for axis in outcome.axes),
        )
        self.assertEqual(
            {"endpoint_face_contact"},
            {contact.recognition_method for contact in outcome.contacts},
        )

    def test_terminal_recovery_rejects_unmatched_offsets_and_directions(self):
        base = _terminal_residual_source({})
        source = replace(
            base,
            primitives=(
                *base.primitives,
                _line((-675.0, 25.0), (-175.0, 25.0), "OFFSET-A"),
                _line((-675.0, 543.0), (-175.0, 543.0), "OFFSET-B"),
                _line((-675.0, 0.0), (-175.0, 25.0), "ANGLE-A"),
                _line((-675.0, 518.0), (-175.0, 543.0), "ANGLE-B"),
            ),
        )

        outcome = recognize_bim_joist(source, _terminal_context())

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(
            (175.0, 175.0),
            tuple(axis.start[0] for axis in outcome.axes),
        )

    def test_compatible_siblings_keep_independent_source_supported_endpoints(self):
        outcome = recognize_bim_joist(
            _terminal_residual_source(),
            _terminal_context(),
        )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(
            (-675.0, -640.0),
            tuple(axis.start[0] for axis in outcome.axes),
        )
        self.assertEqual(
            {"finite_segment_intersection"},
            {contact.recognition_method for contact in outcome.contacts},
        )

    def test_terminal_event_compatibility_uses_inclusive_fifty_mm_boundary(self):
        for second_terminal, expected_status in (
            (-625.0, JoistRecognitionStatus.RECOGNIZED_PAIR),
            (-624.999, JoistRecognitionStatus.AMBIGUOUS),
        ):
            with self.subTest(second_terminal=second_terminal):
                segments = {
                    **{index: ((-675.0, -175.0),) for index in range(3)},
                    **{
                        index: ((second_terminal, -175.0),)
                        for index in range(3, 6)
                    },
                }
                outcome = recognize_bim_joist(
                    _terminal_residual_source(segments),
                    _terminal_context(),
                )
                self.assertEqual(expected_status, outcome.status)
                if expected_status is JoistRecognitionStatus.RECOGNIZED_PAIR:
                    self.assertEqual(
                        (-675.0, -625.0),
                        tuple(axis.start[0] for axis in outcome.axes),
                    )
                else:
                    self.assertEqual(
                        "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
                        outcome.diagnostic_code,
                    )

    def test_multiple_complete_terminal_interpretations_are_order_independent(self):
        segments = {
            index: ((-675.0, -175.0), (-500.0, -175.0))
            for index in range(6)
        }
        source = _terminal_residual_source(segments)
        reversed_source = replace(source, primitives=tuple(reversed(source.primitives)))

        first = recognize_bim_joist(source, _terminal_context())
        second = recognize_bim_joist(reversed_source, _terminal_context())

        self.assertEqual(JoistRecognitionStatus.AMBIGUOUS, first.status)
        self.assertEqual(first.status, second.status)
        self.assertEqual(
            "BIM_JOIST_TERMINAL_RESIDUAL_AMBIGUOUS",
            first.diagnostic_code,
        )
        self.assertEqual(first.diagnostic_code, second.diagnostic_code)
        self.assertEqual((), first.contacts)
        self.assertEqual((), first.pair_relations)

    def test_brace_clipped_fragments_count_as_collective_per_sibling_evidence(self):
        segments = {
            0: ((-675.0, -175.0),),
            1: ((-675.0, -175.0),),
            2: ((-675.0, -175.0),),
            3: ((-640.0, -483.699),),
            4: ((-627.0, -444.724),),
            5: ((-630.0, -627.548),),
        }

        outcome = recognize_bim_joist(
            _terminal_residual_source(segments),
            _terminal_context(),
        )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(
            (-675.0, -640.0),
            tuple(axis.start[0] for axis in outcome.axes),
        )

    def test_final_relation_proof_failure_falls_back_without_preliminary_leak(self):
        relation = JoistPairRelation("S1", "C1", 150.0, 668.0, 518.0, 0.0)
        with patch(
            "dxf_import.joist_recognition._pair_relations",
            side_effect=(
                ((relation,), ""),
                ((), "BIM_JOIST_PAIR_UNPAIRED"),
                ((relation,), ""),
            ),
        ):
            outcome = recognize_bim_joist(
                _terminal_residual_source(),
                _terminal_context(),
            )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(
            (175.0, 175.0),
            tuple(axis.start[0] for axis in outcome.axes),
        )
        self.assertEqual(
            {"endpoint_face_contact"},
            {contact.recognition_method for contact in outcome.contacts},
        )

    def test_final_relation_identity_drift_is_blocking_without_preliminary_truth(self):
        preliminary = JoistPairRelation(
            "S1", "C1", 150.0, 668.0, 518.0, 0.0
        )
        conflicting = JoistPairRelation(
            "S2", "C2", 150.0, 668.0, 518.0, 0.0
        )
        with patch(
            "dxf_import.joist_recognition._pair_relations",
            side_effect=(((preliminary,), ""), ((conflicting,), "")),
        ):
            outcome = recognize_bim_joist(
                _terminal_residual_source(),
                _terminal_context(),
            )

        self.assertEqual(JoistRecognitionStatus.AMBIGUOUS, outcome.status)
        self.assertEqual(
            "BIM_JOIST_TERMINAL_CONTEXT_DRIFT",
            outcome.diagnostic_code,
        )
        self.assertEqual((), outcome.axes)
        self.assertEqual((), outcome.contacts)
        self.assertEqual((), outcome.pair_relations)

    def test_fragmented_lines_continue_to_whole_source_terminal_extent(self):
        source = JoistRecognitionInput(
            root_handle="ROOT",
            root_entity_type="INSERT",
            role="beam",
            primitives=tuple(
                primitive
                for index, offset in enumerate(
                    (0.0, 50.0, 100.0, 518.0, 568.0, 618.0)
                )
                for primitive in (
                    _line((0.0, offset), (400.0, offset), f"A{index}"),
                    _line((600.0, offset), (1000.0, offset), f"B{index}"),
                )
            ),
        )
        context = JoistContextSnapshot(
            struts=(_strut("S1", 800.0),),
            column_stations=(_column("C1", "S1"),),
        )

        outcome = recognize_bim_joist(source, context)

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual((0.0, 1000.0), (
            outcome.axes[0].start[0],
            outcome.axes[0].end[0],
        ))

    def test_single_c_root_requires_a_direct_finite_brace_contact(self):
        brace = JoistMemberReference("B1", (500.0, -100.0), (500.0, 300.0))

        outcome = recognize_bim_joist(
            _single_c_source(),
            JoistContextSnapshot(braces=(brace,)),
        )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_SINGLE, outcome.status)
        self.assertEqual(1, len(outcome.axes))
        self.assertEqual("brace", outcome.contacts[0].member_role)

    def test_importer_maps_brace_contact_without_creating_strut_crossing(self):
        candidate = _Candidate(
            (0.0, 0.0),
            (1000.0, 0.0),
            "bim_joist_single_axis",
            True,
            100.0,
            1.0,
            "BEAM",
            {"ROOT"},
            {"INSERT"},
            [],
            {"ROOT:joist-axis:0"},
            [],
            path_points=((0.0, 0.0), (1000.0, 0.0)),
            joist_assembly_key="ROOT",
            joist_axis_slot=0,
            joist_contacts=(
                JoistContact(
                    0,
                    "brace",
                    "B1",
                    (500.0, 0.0),
                    100.0,
                    (500.0, 0.0),
                ),
            ),
        )

        beam = DXFImporter._make_auxiliary(Beam, "BM", "beam", 1, candidate)

        self.assertEqual((), beam.crossings)
        self.assertEqual(1, len(beam.brace_contacts))
        self.assertEqual("B1", beam.brace_contacts[0].brace_id)
        self.assertEqual((500.0, 0.0), beam.brace_contacts[0].world_point)
        self.assertEqual((), beam.associated_strut_ids)

    def test_l_angle_detail_is_not_promoted_to_a_joist(self):
        source = JoistRecognitionInput(
            "DETAIL",
            "INSERT",
            "beam",
            (
                _line((0.0, 0.0), (1000.0, 0.0), "A"),
                _line((0.0, 50.0), (1000.0, 50.0), "B"),
            ),
        )

        outcome = recognize_bim_joist(source, JoistContextSnapshot())

        self.assertEqual(JoistRecognitionStatus.FAILED, outcome.status)
        self.assertEqual("BIM_JOIST_WHOLE_SOURCE_AXIS_FAILED", outcome.diagnostic_code)

    def test_conflicting_whole_source_directions_are_ambiguous(self):
        horizontal = _double_c_source().primitives
        vertical = tuple(
            _line((offset, 0.0), (offset, 1000.0), f"V{index}")
            for index, offset in enumerate(
                (0.0, 50.0, 100.0, 518.0, 568.0, 618.0)
            )
        )
        source = JoistRecognitionInput(
            "CONFLICT",
            "INSERT",
            "beam",
            (*horizontal, *vertical),
        )

        outcome = recognize_bim_joist(source, JoistContextSnapshot())

        self.assertEqual(JoistRecognitionStatus.AMBIGUOUS, outcome.status)
        self.assertEqual("BIM_JOIST_CONFLICTING_WHOLE_AXES", outcome.diagnostic_code)

    def test_non_insert_or_non_beam_source_is_not_applicable(self):
        for root_type, role in (("LINE", "beam"), ("INSERT", "strut")):
            with self.subTest(root_type=root_type, role=role):
                source = JoistRecognitionInput(
                    "ROOT",
                    root_type,
                    role,
                    _double_c_source().primitives,
                )
                self.assertEqual(
                    JoistRecognitionStatus.NOT_APPLICABLE,
                    recognize_bim_joist(source, JoistContextSnapshot()).status,
                )

    def test_strut_face_contact_preserves_source_axis_and_projects_relation(self):
        context = JoistContextSnapshot(
            struts=(_strut("S1", 0.0, width=350.0),),
            column_stations=(_column("C1", "S1"),),
        )

        outcome = recognize_bim_joist(
            _double_c_source(start=175.0),
            context,
        )

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, outcome.status)
        self.assertEqual(2, len(outcome.contacts))
        for contact, axis in zip(outcome.contacts, outcome.axes):
            self.assertEqual("endpoint_face_contact", contact.recognition_method)
            self.assertEqual(axis.start, contact.source_contact_point)
            self.assertEqual(175.0, contact.source_contact_point[0])
            self.assertEqual(0.0, contact.point[0])
            self.assertEqual(175.0, abs(contact.source_contact_point[0] - contact.point[0]))
            self.assertEqual(175.0, axis.start[0])

    def test_strut_face_contact_tolerance_is_inclusive(self):
        self.assertEqual(25.0, JOIST_STRUT_FACE_CONTACT_TOLERANCE_MM)
        for start, expected in ((150.0, True), (200.0, True), (200.001, False)):
            with self.subTest(start=start):
                context = JoistContextSnapshot(
                    struts=(_strut("S1", 0.0, width=350.0),),
                    column_stations=(_column("C1", "S1"),),
                )
                outcome = recognize_bim_joist(_double_c_source(start=start), context)
                self.assertEqual(
                    JoistRecognitionStatus.RECOGNIZED_PAIR if expected
                    else JoistRecognitionStatus.FAILED,
                    outcome.status,
                )

    def test_face_contact_rejects_missing_width_and_brace_extension(self):
        no_width = JoistContextSnapshot(
            struts=(_strut("S1", 0.0, width=0.0),),
            column_stations=(_column("C1", "S1"),),
        )
        brace_only = JoistContextSnapshot(
            braces=(JoistMemberReference("B1", (0.0, -100.0), (0.0, 800.0)),),
        )

        self.assertEqual(
            JoistRecognitionStatus.FAILED,
            recognize_bim_joist(_double_c_source(start=175.0), no_width).status,
        )
        outcome = recognize_bim_joist(_single_c_source(start=175.0), brace_only)
        self.assertEqual(JoistRecognitionStatus.FAILED, outcome.status)
        self.assertEqual("BIM_JOIST_SINGLE_NO_BRACE_CONTACT", outcome.diagnostic_code)

    def test_multiple_eligible_struts_at_one_terminal_is_blocking_ambiguity(self):
        context = JoistContextSnapshot(
            struts=(
                _strut("S1", 0.0, width=350.0),
                _strut("S2", 0.0, width=350.0),
            ),
        )

        outcome = recognize_bim_joist(_double_c_source(start=175.0), context)

        self.assertEqual(JoistRecognitionStatus.AMBIGUOUS, outcome.status)
        self.assertEqual(
            "BIM_JOIST_STRUT_FACE_CONTACT_AMBIGUOUS",
            outcome.diagnostic_code,
        )

    def test_pair_requires_one_unique_eligible_column(self):
        strut = _strut("S1", 500.0)
        missing = recognize_bim_joist(
            _double_c_source(),
            JoistContextSnapshot(struts=(strut,)),
        )
        ambiguous = recognize_bim_joist(
            _double_c_source(),
            JoistContextSnapshot(
                struts=(strut,),
                column_stations=(
                    _column("C1", "S1", 408.0),
                    _column("C2", "S1", 410.0),
                ),
            ),
        )

        self.assertEqual(JoistRecognitionStatus.FAILED, missing.status)
        self.assertEqual("BIM_JOIST_PAIR_UNPAIRED", missing.diagnostic_code)
        self.assertEqual(JoistRecognitionStatus.AMBIGUOUS, ambiguous.status)
        self.assertEqual("BIM_JOIST_PAIR_AMBIGUOUS", ambiguous.diagnostic_code)

    def test_face_contact_rejects_oblique_and_infinite_only_intersections(self):
        oblique = JoistMemberReference(
            "S1",
            (0.0, -100.0),
            (100.0, 800.0),
            source_width=350.0,
        )
        remote = JoistMemberReference(
            "S1",
            (0.0, 1000.0),
            (0.0, 2000.0),
            source_width=350.0,
        )
        for member in (oblique, remote):
            with self.subTest(member=member):
                outcome = recognize_bim_joist(
                    _double_c_source(start=175.0),
                    JoistContextSnapshot(
                        struts=(member,),
                        column_stations=(_column("C1", "S1"),),
                    ),
                )
                self.assertEqual(JoistRecognitionStatus.FAILED, outcome.status)

    def test_primitive_and_line_direction_order_do_not_change_axes(self):
        source = _double_c_source()
        reversed_source = JoistRecognitionInput(
            source.root_handle,
            source.root_entity_type,
            source.role,
            tuple(
                JoistPrimitive(
                    tuple(reversed(primitive.points)),
                    primitive.closed,
                    primitive.entity_type,
                    primitive.source_handle,
                )
                for primitive in reversed(source.primitives)
            ),
        )
        context = JoistContextSnapshot(
            struts=(_strut("S1", 500.0),),
            column_stations=(_column("C1", "S1"),),
        )

        first = recognize_bim_joist(source, context)
        second = recognize_bim_joist(reversed_source, context)

        self.assertEqual(first.status, second.status)
        self.assertEqual(first.axes, second.axes)
        self.assertEqual(first.pair_relations, second.pair_relations)


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF test asset unavailable")
class Y05BIMJoistCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y05_DXF_PATH).read()
        cls.layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[label]
            for layer, label in Y05_LAYER_MAPPING.items()
            if layer in cls.importer.layer_names
        }
        cls.result = cls.importer.convert(layer_roles=cls.layer_roles)
        cls.strut_id_by_source_handle = {
            handle.upper(): strut.id
            for strut in cls.result.struts
            for handle in strut.source_handles
        }
        beam_layer = next(
            layer for layer, role in cls.layer_roles.items() if role == "beam"
        )
        cls.groups = cls.importer._geometry_groups(
            "beam",
            beam_layer,
            cls.importer.entities_on_layer(beam_layer),
            [],
            [],
        )
        context = JoistContextSnapshot(
            struts=tuple(
                JoistMemberReference(
                    strut.id,
                    strut.start,
                    strut.end,
                    strut.source_handles,
                    strut.source_width,
                )
                for strut in cls.result.struts
            ),
            braces=tuple(
                JoistMemberReference(
                    brace.id,
                    brace.start,
                    brace.end,
                    brace.source_handles,
                    brace.source_width,
                )
                for brace in cls.result.braces
            ),
            column_stations=tuple(
                JoistColumnStationReference(
                    column.id,
                    column.associated_strut_id,
                    column.association_station,
                )
                for column in cls.result.columns
                if column.associated_strut_id
                and column.association_station is not None
            ),
        )
        cls.outcomes = {
            (group.root_handle or "").upper(): recognize_bim_joist(
                _recognition_source_from_group(group),
                context,
                cls.importer.tolerances,
            )
            for group in cls.groups
        }

    def test_y05_source_population_and_formal_joist_count(self):
        status_counts = {
            status: sum(
                outcome.status is status for outcome in self.outcomes.values()
            )
            for status in JoistRecognitionStatus
        }

        self.assertEqual(84, len(self.groups))
        self.assertEqual(20, status_counts[JoistRecognitionStatus.RECOGNIZED_PAIR])
        self.assertEqual(18, status_counts[JoistRecognitionStatus.RECOGNIZED_SINGLE])
        self.assertEqual(46, status_counts[JoistRecognitionStatus.FAILED])
        self.assertEqual(
            58,
            sum(len(outcome.axes) for outcome in self.outcomes.values()),
        )

    def test_y05_pair_relations_match_characterized_station_contract(self):
        pair_outcomes = tuple(
            outcome
            for outcome in self.outcomes.values()
            if outcome.status is JoistRecognitionStatus.RECOGNIZED_PAIR
        )
        relations = tuple(
            relation
            for outcome in pair_outcomes
            for relation in outcome.pair_relations
        )
        endpoint_contacts = tuple(
            contact
            for outcome in pair_outcomes
            for contact in outcome.contacts
            if contact.recognition_method == "endpoint_face_contact"
        )
        direct_contacts = tuple(
            contact
            for outcome in pair_outcomes
            for contact in outcome.contacts
            if contact.recognition_method == "finite_segment_intersection"
        )

        self.assertEqual(68, len(relations))
        self.assertEqual(0, len(endpoint_contacts))
        self.assertEqual(136, len(direct_contacts))
        self.assertGreaterEqual(min(item.spacing for item in relations), 518.0 - 1e-3)
        self.assertLessEqual(max(item.spacing for item in relations), 518.001)
        self.assertLessEqual(
            max(abs(item.midpoint_error) for item in relations),
            0.942 + 1e-3,
        )

    def test_y05_relation_inventory_is_checked_per_root_and_strut(self):
        expected = {
            "E8F": ("CD6", "CF9", "D0A", "D16"),
            "E90": ("CD6", "CF9", "D0A", "D16"),
            "E91": ("D17", "D18", "D19", "D1A"),
            "E92": ("D17", "D18", "D19", "D1A"),
            "EB8": ("D1B", "D1C", "D1D", "D29"),
            "EB9": ("D1B", "D1C", "D1D", "D29"),
            "ED9": ("D34", "D4B", "D74"),
            "EF9": ("D34", "D4B", "D74"),
            "F2A": ("CD6", "CF9", "D0A", "D16"),
            "F2B": ("D17", "D18", "D19", "D1A"),
            "F51": ("D1B", "D1C", "D1D", "D29"),
            "F82": ("D34", "D4B", "D74"),
            "14D3": ("CD6", "CF9", "D0A", "D16"),
            "14D4": ("D17", "D18", "D19", "D1A"),
            "14D5": ("D1B", "D1C", "D1D", "D29"),
            "14D6": ("D34", "D4B", "D74"),
            "14F4": ("91D", "963"),
            "1512": ("91D", "963"),
            "15D4": ("ACB", "B11"),
            "15F2": ("ACB", "B11"),
        }

        for root_handle, strut_source_handles in expected.items():
            with self.subTest(root_handle=root_handle):
                strut_ids = tuple(
                    self.strut_id_by_source_handle[source_handle]
                    for source_handle in strut_source_handles
                )
                outcome = self.outcomes[root_handle]
                relations = {item.strut_id: item for item in outcome.pair_relations}
                self.assertEqual(set(strut_ids), set(relations))
                for relation in relations.values():
                    contacts = tuple(
                        item
                        for item in outcome.contacts
                        if item.member_role == "strut"
                        and item.member_id == relation.strut_id
                    )
                    self.assertEqual(2, len(contacts))
                    self.assertTrue(relation.column_id)
                    self.assertTrue(pair_spacing_is_eligible(relation.spacing))
                    self.assertLessEqual(abs(relation.midpoint_error), 2.0)
                    self.assertEqual(
                        {"finite_segment_intersection"},
                        {item.recognition_method for item in contacts},
                    )
                    for contact in contacts:
                        self.assertEqual(
                            contact.source_contact_point,
                            contact.point,
                        )

    def test_e8f_uses_large_root_axes_and_small_overlaps_remain_details(self):
        e8f = self.outcomes["E8F"]
        first_main_strut_id = self.strut_id_by_source_handle["CD6"]
        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, e8f.status)
        self.assertEqual(2, len(e8f.axes))
        self.assertEqual(
            (-36173.5, -36173.5),
            tuple(round(axis.start[0], 3) for axis in e8f.axes),
        )
        first_main_strut_contacts = tuple(
            contact
            for contact in e8f.contacts
            if contact.member_id == first_main_strut_id
        )
        self.assertEqual(2, len(first_main_strut_contacts))
        self.assertEqual(
            {"finite_segment_intersection"},
            {
                contact.recognition_method
                for contact in first_main_strut_contacts
            },
        )
        for contact in first_main_strut_contacts:
            self.assertEqual(contact.source_contact_point, contact.point)
        for handle in ("16BC", "16C6", "16DF", "16E0"):
            with self.subTest(handle=handle):
                self.assertEqual(
                    JoistRecognitionStatus.FAILED,
                    self.outcomes[handle].status,
                )

    def test_f2a_keeps_per_sibling_source_supported_terminal_endpoints(self):
        f2a = self.outcomes["F2A"]

        self.assertEqual(JoistRecognitionStatus.RECOGNIZED_PAIR, f2a.status)
        self.assertEqual(
            (-36173.5, -36127.267),
            tuple(round(axis.start[0], 3) for axis in f2a.axes),
        )
        self.assertLessEqual(
            abs(f2a.axes[1].start[0] - f2a.axes[0].start[0]),
            50.0,
        )
        self.assertNotEqual(f2a.axes[0].start[0], f2a.axes[1].start[0])

    def test_y05_importer_emits_58_beams_and_validated_crossings(self):
        self.assertEqual(58, len(self.result.beams))
        self.assertEqual(136, len(self.result.beam_crossings))
        self.assertEqual(
            0,
            sum(
                crossing.recognition_method == "endpoint_face_contact"
                for crossing in self.result.beam_crossings
            ),
        )
        self.assertEqual(
            136,
            sum(
                crossing.recognition_method == "finite_segment_intersection"
                for crossing in self.result.beam_crossings
            ),
        )
        self.assertEqual(
            {"bim_joist_paired_axis", "bim_joist_single_axis"},
            {beam.recognition_method for beam in self.result.beams},
        )
        self.assertEqual(
            40,
            sum(
                beam.recognition_method == "bim_joist_paired_axis"
                for beam in self.result.beams
            ),
        )
        self.assertEqual(
            18,
            sum(
                beam.recognition_method == "bim_joist_single_axis"
                for beam in self.result.beams
            ),
        )

        e8f = tuple(
            beam for beam in self.result.beams if "E8F" in beam.source_handles
        )
        self.assertEqual(2, len(e8f))
        self.assertEqual({0, 1}, {beam.joist_axis_slot for beam in e8f})
        first_main_strut_id = self.strut_id_by_source_handle["CD6"]
        for beam in e8f:
            first_main_strut_crossing = next(
                crossing
                for crossing in beam.crossings
                if crossing.strut_id == first_main_strut_id
            )
            self.assertEqual(
                "finite_segment_intersection",
                first_main_strut_crossing.recognition_method,
            )
            self.assertIsNotNone(
                first_main_strut_crossing.world_source_contact_point
            )
            self.assertAlmostEqual(
                0.0,
                first_main_strut_crossing.distance,
                places=3,
            )

    def test_y05_validated_crossings_drive_runtime_associations(self):
        beam_associations = tuple(
            item
            for item in self.result.component_associations
            if item.component_role == "beam"
        )
        crossing_keys = {
            (crossing.beam_id, crossing.strut_id, round(crossing.strut_station, 6))
            for crossing in self.result.beam_crossings
        }
        association_keys = {
            (item.component_id, item.strut_id, round(item.station, 6))
            for item in beam_associations
        }

        self.assertEqual(136, len(beam_associations))
        self.assertEqual(crossing_keys, association_keys)
        e8f_ids = {
            beam.id for beam in self.result.beams if "E8F" in beam.source_handles
        }
        first_main_strut_id = self.strut_id_by_source_handle["CD6"]
        first_main_strut = next(
            strut
            for strut in self.result.struts
            if strut.id == first_main_strut_id
        )
        self.assertTrue(
            e8f_ids.issubset(set(first_main_strut.associated_beams))
        )
        self.assertEqual(2, len({
            round(crossing.strut_station, 6)
            for crossing in self.result.beam_crossings
            if crossing.beam_id in e8f_ids
            and crossing.strut_id == first_main_strut_id
        }))
        self.assertTrue(
            all("JoistAssembly" not in beam.to_project_row() for beam in self.result.beams)
        )

    def test_y05_project_projection_keeps_both_beam_ids_and_stations(self):
        # Unrelated Waler/CornerBrace fixture errors do not participate in this
        # focused Beam projection assertion.
        projection_source = replace(
            self.result,
            messages=tuple(
                message
                for message in self.result.messages
                if message.severity not in {"error", "critical"}
            ),
        )
        rows = projection_source.to_project_rows()
        first_main_strut_id = self.strut_id_by_source_handle["CD6"]
        first_main_strut_row = next(
            row
            for row in rows["struts"]
            if row["StrutID"] == first_main_strut_id
        )
        e8f = tuple(
            beam for beam in self.result.beams if "E8F" in beam.source_handles
        )

        projected_ids = set(
            first_main_strut_row["AssociatedBeamIDs"].split(",")
        )
        self.assertTrue({beam.id for beam in e8f}.issubset(projected_ids))
        projected_stations = {
            float(value)
            for value in str(first_main_strut_row["BeamPositions"]).split(",")
            if str(value).strip()
        }
        e8f_stations = {
            round(crossing.strut_station)
            for beam in e8f
            for crossing in beam.crossings
            if crossing.strut_id == first_main_strut_id
        }
        self.assertTrue(e8f_stations.issubset(projected_stations))

    def test_finalized_direct_source_and_engineering_points_transform_together(self):
        localized = apply_coordinate_system(
            self.result,
            CoordinateSystem("local", 1000.0, -2000.0, "test"),
        )
        crossing = next(
            item
            for item in localized.beam_crossings
            if item.recognition_method == "finite_segment_intersection"
        )

        self.assertIsNotNone(crossing.world_source_contact_point)
        self.assertEqual(crossing.world_point, crossing.world_source_contact_point)
        self.assertEqual(
            (
                crossing.world_source_contact_point[0] - 1000.0,
                crossing.world_source_contact_point[1] + 2000.0,
            ),
            crossing.local_source_contact_point,
        )
        self.assertEqual(
            (crossing.world_point[0] - 1000.0, crossing.world_point[1] + 2000.0),
            crossing.local_point,
        )

    def test_y05_review_has_one_selectable_item_per_formal_joist(self):
        items = build_review_items(self.result)
        beam_items = tuple(item for item in items if item.role == "beam")

        self.assertEqual(58, len(beam_items))
        self.assertTrue(all(item.status == "recognized" for item in beam_items))
        self.assertEqual(58, len({item.member_id for item in beam_items}))
        self.assertFalse(
            any(
                handle in {"16BC", "16C6", "16DF", "16E0"}
                for item in beam_items
                for handle in item.source_handles
            )
        )

    def test_y05_paired_root_exclusion_and_restore_are_atomic(self):
        excluded = self.importer.convert(
            layer_roles=self.layer_roles,
            excluded_sources=(ExcludedSource("beam", ("E8F",)),),
        )
        restored = self.importer.convert(layer_roles=self.layer_roles)

        self.assertEqual(56, len(excluded.beams))
        self.assertFalse(
            any("E8F" in beam.source_handles for beam in excluded.beams)
        )
        self.assertEqual(58, len(restored.beams))
        self.assertEqual(
            2,
            sum("E8F" in beam.source_handles for beam in restored.beams),
        )


@unittest.skipUnless(
    Y1A_DXF_PATH.is_file() and Y29_DXF_PATH.is_file(),
    "Y1A/Y29 DXF fixtures unavailable",
)
class LegacyBeamAssetRegressionTests(unittest.TestCase):
    def test_y1a_and_y29_beam_geometry_and_associations_stay_on_legacy_routes(self):
        cases = (
            (
                Y1A_DXF_PATH,
                Y1A_LAYER_MAPPING,
                20,
                {"mline_center_path": 20},
                60,
                (
                    ("BM1", (349788.287, -711843.7), (369788.287, -710993.7)),
                    ("BM20", (429585.787, -716547.569), (434288.287, -716547.569)),
                ),
            ),
            (
                Y29_DXF_PATH,
                Y29_LAYER_MAPPING,
                56,
                {"mline_center_path": 40, "closed_outline_axis": 16},
                279,
                (
                    ("BM1", (315460.79, -430353.499), (323114.664, -430353.499)),
                    ("BM56", (281300.157, -455777.157), (282965.843, -457442.843)),
                ),
            ),
        )
        for path, mapping, beam_count, methods, crossings, endpoint_samples in cases:
            with self.subTest(path=path.name):
                importer = DXFImporter(path).read()
                layer_roles = {
                    layer: DXFImportDialog.USE_TO_ROLE[label]
                    for layer, label in mapping.items()
                    if layer in importer.layer_names
                }
                result = importer.convert(layer_roles=layer_roles)
                beam_associations = tuple(
                    item
                    for item in result.component_associations
                    if item.component_role == "beam"
                )

                self.assertEqual(beam_count, len(result.beams))
                self.assertEqual(
                    methods,
                    dict(Counter(beam.recognition_method for beam in result.beams)),
                )
                self.assertEqual(crossings, len(result.beam_crossings))
                self.assertEqual(crossings, len(beam_associations))
                by_id = {beam.id: beam for beam in result.beams}
                for beam_id, expected_start, expected_end in endpoint_samples:
                    beam = by_id[beam_id]
                    self.assertEqual(
                        expected_start,
                        tuple(round(value, 3) for value in beam.start),
                    )
                    self.assertEqual(
                        expected_end,
                        tuple(round(value, 3) for value in beam.end),
                    )
                self.assertFalse(
                    any(
                        message.code.startswith("BIM_JOIST_TERMINAL_")
                        for message in result.messages
                    )
                )
                self.assertFalse(
                    any(beam.joist_assembly_key for beam in result.beams)
                )


if __name__ == "__main__":
    unittest.main()
