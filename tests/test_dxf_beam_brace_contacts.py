from __future__ import annotations

import math
import unittest
from dataclasses import replace

from dxf_import.beam_contacts import finite_perpendicular_contact
from dxf_import.candidate_points import (
    associate_components_to_struts,
    rebuild_component_associations,
)
from dxf_import.models import (
    Beam,
    BeamBraceContact,
    BeamCrossing,
    Brace,
    CoordinateSystem,
    DXFImportResult,
    GeometryTolerances,
    Strut,
    apply_coordinate_system,
)
from dxf_import.review_confirmation import review_confirmation_signature
from dxf_import.validation import build_review_items


def _beam(**changes) -> Beam:
    values = {
        "id": "BM1",
        "start": (10.0, 20.0),
        "end": (110.0, 20.0),
        "source_layer": "BEAM",
        "source_handles": ("HBM1",),
        "source_entity_types": ("LINE",),
        "recognition_method": "existing_centerline",
        "centerline_computed": False,
        "source_width": 100.0,
        "confidence": 1.0,
        "world_path": ((10.0, 20.0), (110.0, 20.0)),
    }
    values.update(changes)
    return Beam(**values)


def _brace(identifier: str = "B1", *, x: float = 50.0) -> Brace:
    return Brace(
        id=identifier,
        start=(x, -50.0),
        end=(x, 50.0),
        source_layer="BRACE",
        source_handles=(f"H{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=100.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
    )


def _strut(identifier: str = "S1", *, x: float = 50.0) -> Strut:
    return Strut(
        id=identifier,
        start=(x, -50.0),
        end=(x, 50.0),
        source_layer="STRUT",
        source_handles=(f"H{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=100.0,
        from_waler="W1",
        to_waler="W2",
        confidence=1.0,
    )


def _result(
    beam: Beam,
    *,
    braces: tuple[Brace, ...] = (),
    struts: tuple[Strut, ...] = (),
) -> DXFImportResult:
    return DXFImportResult(
        source_path="contacts.dxf",
        layer_names=("BEAM",),
        selected_layers={},
        layer_info=(),
        walers=(),
        struts=struts,
        braces=braces,
        columns=(),
        beams=(beam,),
        corner_braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={},
    )


class BeamContactGeometryTests(unittest.TestCase):
    def test_five_degree_boundary_and_shared_endpoint_are_valid(self):
        angle = math.radians(85.0)
        member = (
            (10.0, 0.0),
            (10.0 + 10.0 * math.cos(angle), 10.0 * math.sin(angle)),
        )

        contact = finite_perpendicular_contact(((0.0, 0.0), (10.0, 0.0)), member)

        self.assertIsNotNone(contact)
        assert contact is not None
        self.assertAlmostEqual(10.0, contact[0][0])
        self.assertAlmostEqual(0.0, contact[0][1])
        self.assertAlmostEqual(0.0, contact[1])

    def test_angle_beyond_five_degrees_is_rejected(self):
        angle = math.radians(84.999)
        member = (
            (5.0, -5.0),
            (5.0 + 10.0 * math.cos(angle), -5.0 + 10.0 * math.sin(angle)),
        )

        self.assertIsNone(
            finite_perpendicular_contact(((0.0, 0.0), (10.0, 0.0)), member)
        )

    def test_gap_projection_nearest_point_and_infinite_extension_are_rejected(self):
        subject = ((0.0, 0.0), (10.0, 0.0))

        self.assertIsNone(
            finite_perpendicular_contact(subject, ((11.0, -1.0), (11.0, 1.0)))
        )
        self.assertIsNone(
            finite_perpendicular_contact(subject, ((5.0, 1.0), (5.0, 3.0)))
        )


class BeamBraceContactModelTests(unittest.TestCase):
    def test_contact_is_runtime_only_and_does_not_create_strut_state(self):
        contact = BeamBraceContact(
            beam_id="BM1",
            brace_id="B1",
            world_point=(50.0, 20.0),
            local_point=(50.0, 20.0),
            beam_segment_index=0,
        )
        beam = _beam(brace_contacts=(contact,))

        row = beam.to_project_row()

        self.assertNotIn("BraceContacts", row)
        self.assertNotIn("brace_contacts", row)
        self.assertEqual((), beam.crossings)
        self.assertEqual((), beam.associated_strut_ids)
        self.assertEqual("", beam.associated_strut_id)

    def test_coordinate_transform_rebuilds_local_point_from_world_point(self):
        contact = BeamBraceContact(
            beam_id="BM1",
            brace_id="B1",
            world_point=(50.0, 20.0),
            local_point=(999.0, 999.0),
            beam_segment_index=0,
        )

        transformed = apply_coordinate_system(
            _result(_beam(brace_contacts=(contact,))),
            CoordinateSystem("local", 10.0, 5.0, "test"),
        )

        actual = transformed.beams[0].brace_contacts[0]
        self.assertEqual((50.0, 20.0), actual.world_point)
        self.assertEqual((40.0, 15.0), actual.local_point)
        self.assertEqual("B1", actual.brace_id)

    def test_confirmation_signature_changes_with_contact_engineering_identity(self):
        contact = BeamBraceContact(
            beam_id="BM1",
            brace_id="B1",
            world_point=(50.0, 20.0),
            local_point=(50.0, 20.0),
            beam_segment_index=0,
        )
        result = _result(_beam(brace_contacts=(contact,)))
        item = next(item for item in build_review_items(result) if item.member_id == "BM1")
        original = review_confirmation_signature(result, item)

        changed_contact = replace(contact, world_point=(51.0, 20.0))
        changed_result = replace(
            result,
            beams=(replace(result.beams[0], brace_contacts=(changed_contact,)),),
        )

        self.assertIsNotNone(original)
        self.assertNotEqual(original, review_confirmation_signature(changed_result, item))


class BeamBraceAssociationTests(unittest.TestCase):
    def _associate(self, beam, *, struts=(), braces=()):
        return associate_components_to_struts(
            struts,
            (),
            (beam,),
            GeometryTolerances(),
            braces=braces,
        )

    def test_crossing_only_is_connected_and_preserves_strut_projection(self):
        strut = _strut()

        associated_struts, _, beams, records, messages = self._associate(
            _beam(),
            struts=(strut,),
        )

        self.assertEqual(1, len(beams[0].crossings))
        self.assertEqual((), beams[0].brace_contacts)
        self.assertFalse(any(item.code == "BEAM_NOT_ASSOCIATED" for item in messages))
        self.assertEqual(("BM1",), associated_struts[0].associated_beams)
        self.assertEqual(1, len(records))

    def test_brace_contact_only_is_connected_without_strut_constraints(self):
        associated_struts, _, beams, records, messages = self._associate(
            _beam(),
            braces=(_brace(),),
        )

        self.assertEqual((), associated_struts)
        self.assertEqual((), beams[0].crossings)
        self.assertEqual(1, len(beams[0].brace_contacts))
        self.assertEqual((), records)
        self.assertFalse(any(item.code == "BEAM_NOT_ASSOCIATED" for item in messages))

    def test_no_crossing_or_brace_contact_emits_warning(self):
        _, _, beams, _, messages = self._associate(_beam())

        self.assertEqual((), beams[0].crossings)
        self.assertEqual((), beams[0].brace_contacts)
        self.assertEqual(
            1,
            sum(item.code == "BEAM_NOT_ASSOCIATED" for item in messages),
        )

    def test_adjacent_segments_shared_vertex_produces_one_contact(self):
        beam = _beam(
            start=(0.0, 0.0),
            end=(20.0, 0.0),
            world_path=((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)),
        )

        _, _, beams, _, _ = self._associate(
            beam,
            braces=(_brace(x=10.0),),
        )

        self.assertEqual(1, len(beams[0].brace_contacts))
        self.assertEqual((10.0, 0.0), beams[0].brace_contacts[0].world_point)
        self.assertEqual(0, beams[0].brace_contacts[0].beam_segment_index)

    def test_same_beam_and_brace_can_keep_two_distinct_contact_points(self):
        beam = _beam(
            start=(0.0, 0.0),
            end=(0.0, 10.0),
            world_path=(
                (0.0, 0.0),
                (20.0, 0.0),
                (20.0, 10.0),
                (0.0, 10.0),
            ),
        )

        _, _, beams, _, _ = self._associate(
            beam,
            braces=(_brace(x=10.0),),
        )

        self.assertEqual(
            ((10.0, 0.0), (10.0, 10.0)),
            tuple(item.world_point for item in beams[0].brace_contacts),
        )

    def test_path_and_brace_order_do_not_change_engineering_contacts_or_warning(self):
        forward = _beam(
            start=(0.0, 0.0),
            end=(20.0, 0.0),
            world_path=((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)),
        )
        reverse = replace(
            forward,
            start=(20.0, 0.0),
            end=(0.0, 0.0),
            world_start=(20.0, 0.0),
            world_end=(0.0, 0.0),
            world_path=tuple(reversed(forward.world_path)),
        )
        braces = (_brace("B2", x=15.0), _brace("B1", x=10.0))

        first = self._associate(forward, braces=braces)
        second = self._associate(reverse, braces=tuple(reversed(braces)))
        first_contacts = tuple(
            (item.brace_id, item.world_point)
            for item in first[2][0].brace_contacts
        )
        second_contacts = tuple(
            (item.brace_id, item.world_point)
            for item in second[2][0].brace_contacts
        )

        self.assertEqual(first_contacts, second_contacts)
        self.assertEqual(
            [item.code for item in first[4]],
            [item.code for item in second[4]],
        )

    def test_rebuild_recomputes_contacts_from_current_formal_braces(self):
        initial = _result(_beam(), braces=(_brace(),))
        built = rebuild_component_associations(initial)
        rebuilt = rebuild_component_associations(built)

        self.assertEqual(
            built.beams[0].brace_contacts,
            rebuilt.beams[0].brace_contacts,
        )

        without_brace = rebuild_component_associations(
            replace(rebuilt, braces=())
        )
        self.assertEqual((), without_brace.beams[0].brace_contacts)
        self.assertTrue(
            any(
                item.code == "BEAM_NOT_ASSOCIATED"
                for item in without_brace.messages
            )
        )

    def test_brace_contact_does_not_add_any_strut_or_project_derived_state(self):
        stale_crossing = BeamCrossing(
            "BM1", "MISSING", (50.0, 20.0), (50.0, 20.0), 50.0, 0
        )
        beam = _beam(crossings=(stale_crossing,), associated_strut_ids=("MISSING",))

        struts, _, beams, records, _ = self._associate(
            beam,
            braces=(_brace(),),
        )

        self.assertEqual((), struts)
        self.assertEqual((), records)
        self.assertEqual((), beams[0].crossings)
        self.assertEqual((), beams[0].associated_strut_ids)
        self.assertEqual("", beams[0].associated_strut_id)

    def test_brace_contact_does_not_feed_project_or_solver_station_fields(self):
        distant_strut = _strut(x=500.0)
        rebuilt = rebuild_component_associations(
            _result(
                _beam(),
                braces=(_brace(),),
                struts=(distant_strut,),
            )
        )

        self.assertEqual((), rebuilt.component_associations)
        self.assertEqual((), rebuilt.struts[0].beam_positions)
        self.assertEqual((), rebuilt.struts[0].associated_beams)
        strut_row = rebuilt.to_project_rows()["struts"][0]
        self.assertEqual("", strut_row["BeamPositions"])
        self.assertEqual("", strut_row["AssociatedBeamIDs"])


if __name__ == "__main__":
    unittest.main()
