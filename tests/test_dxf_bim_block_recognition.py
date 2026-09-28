from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ezdxf

from bracing_optimizer.application.project_data import ProjectDataModel
from dxf_import.candidate_points import set_cad_engineering_line
from dxf_import.importer import DXFImporter, Y1A_LAYER_MAPPING, Y29_LAYER_MAPPING
from dxf_import.block_member_recognition import (
    BlockMemberPrimitive,
    BlockMemberRecognitionInput,
    BlockMemberRecognitionOutcome,
    BlockMemberRecognitionStatus,
    FragmentEvidenceKind,
    WalerSpanReference,
    _build_orientation_clusters,
    _component_candidates,
    _extract_fragment_axes,
    _extract_topology_members,
    _whole_root_envelope_candidates,
    recognize_component_like_member,
    recognize_component_like_strut,
)
from dxf_import.models import ExcludedSource, GeometryTolerances
from dxf_import.recognition import (
    _Candidate,
    _GeometryGroup,
    _Primitive,
    _candidate_from_group,
    _build_waler_span_context,
    _deduplicate_candidates,
    _engineering_line_candidates,
    _finalize_contextual_strut_waler_spans,
    _route_component_like_member_block,
    _route_component_like_strut_block,
)
from dxf_import.review_confirmation import (
    confirm_review_item,
    review_confirmation_identity,
    review_item_is_confirmed,
    valid_review_confirmations,
)
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import (
    capture_manual_overrides,
    excluded_source_from_review_item,
    replay_manual_overrides,
)
from dxf_import.validation import build_problem_records, build_review_items


STRUT_LAYER = "STRUT"
BRACE_LAYER = "BRACE"
WALER_LAYER = "WALER"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
Y05_DXF_PATH = next(PROJECT_ROOT.glob("670-CO-Y05*.dxf"), None)
Y1A_DXF_PATH = PROJECT_ROOT / "Y1A擋土支撐簡化版.dxf"
Y29_DXF_PATH = PROJECT_ROOT / "Y29_test.dxf"
Y05_LAYER_ROLES = {
    "I-WALL": "continuous_wall",
    "0": "continuous_wall",
    "圍令": "waler",
    "支撐": "strut",
    "托梁": "beam",
    "斜撐": "brace",
    "S-BEAM": "corner_brace",
    "S-GRID": "auxiliary",
    "S-GRID-IDEN": "auxiliary",
    "S-COLS": "column",
}
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


def _available_internal_layer_roles(importer, mapping):
    return {
        layer: LAYER_USE_TO_ROLE[use]
        for layer, use in mapping.items()
        if layer in importer.layer_names
    }


def _new_document():
    document = ezdxf.new("R2010")
    for layer in (STRUT_LAYER, BRACE_LAYER, WALER_LAYER):
        document.layers.add(layer)
    return document


def _add_rectangle(block, start: float, end: float, width: float) -> None:
    half_width = width / 2.0
    block.add_lwpolyline(
        (
            (start, -half_width),
            (end, -half_width),
            (end, half_width),
            (start, half_width),
        ),
        close=True,
    )


def _add_ordinary_insert(document):
    block = document.blocks.new("ORDINARY_STRUT_BLOCK")
    block.add_line((0.0, 0.0), (12000.0, 0.0))
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_ordinary_compound_insert(document):
    block = document.blocks.new("ORDINARY_COMPOUND_STRUT_BLOCK")
    block.add_line((0.0, 0.0), (1800.0, 250.0))
    block.add_line((500.0, -600.0), (750.0, 1600.0))
    block.add_line((2300.0, 850.0), (3050.0, 1200.0))
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_complete_outline_insert(document):
    block = document.blocks.new("COMPLETE_STRUT_OUTLINE")
    _add_rectangle(block, 0.0, 12000.0, 400.0)
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_fragmented_strut_insert(document):
    block = document.blocks.new("FRAGMENTED_STRUT")
    for start, end in (
        (0.0, 2200.0),
        (3100.0, 5200.0),
        (6800.0, 8900.0),
        (10100.0, 12000.0),
    ):
        _add_rectangle(block, start, end, 400.0)
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_fragmented_brace_insert(document):
    block = document.blocks.new("FRAGMENTED_BRACE")
    for start, end in (
        (0.0, 2200.0),
        (3100.0, 5200.0),
        (6800.0, 8900.0),
        (10100.0, 12000.0),
    ):
        _add_rectangle(block, start, end, 300.0)
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": BRACE_LAYER},
    )


def _add_single_line_insert(document, *, block_name: str, root_layer: str):
    block = document.blocks.new(block_name)
    block.add_line((0.0, 0.0), (12000.0, 0.0), dxfattribs={"layer": "0"})
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": root_layer},
    )


def _extract_groups(document, *, role: str, layer: str):
    importer = DXFImporter("synthetic-bim-block.dxf")
    importer._document = document
    debug = []
    source_geometry = []
    groups = importer._geometry_groups(
        role,
        layer,
        importer.entities_on_layer(layer),
        debug,
        source_geometry,
    )
    return groups, source_geometry


def _extract_strut_groups(document):
    return _extract_groups(document, role="strut", layer=STRUT_LAYER)


def _recognition_source_from_group(group):
    return BlockMemberRecognitionInput(
        root_handle=group.root_handle or "",
        root_entity_type=group.root_entity_type,
        role=group.role,
        primitives=tuple(
            BlockMemberPrimitive(
                points=tuple(primitive.points),
                closed=primitive.closed,
                entity_type=primitive.entity_type,
                source_handle=primitive.source_handle,
                source_width=primitive.source_width,
            )
            for primitive in group.primitives
        ),
    )


def _y05_brace_characterization():
    """Return deterministic per-root evidence from the real Y05 Brace layer."""

    if Y05_DXF_PATH is None:
        raise FileNotFoundError("Y05 DXF test asset is unavailable")
    importer = DXFImporter(Y05_DXF_PATH).read()
    groups = importer._geometry_groups(
        "brace",
        "斜撐",
        importer.entities_on_layer("斜撐"),
        [],
        [],
    )
    result = importer.convert(layer_roles=Y05_LAYER_ROLES)
    records = []
    for group in groups:
        source = _recognition_source_from_group(group)
        outcome = recognize_component_like_member(source, importer.tolerances)
        general_candidate, general_messages = _candidate_from_group(
            group,
            "brace",
            importer.tolerances,
        )
        source_handle = source.root_handle
        members = tuple(
            member
            for member in result.braces
            if source_handle in member.source_handles
        )
        records.append(
            {
                "source_handle": source_handle,
                "root_entity_type": group.root_entity_type,
                "primitive_count": len(group.primitives),
                "general": (
                    None
                    if general_candidate is None
                    else (
                        general_candidate.recognition_method,
                        general_candidate.start,
                        general_candidate.end,
                        general_candidate.source_width,
                    )
                ),
                "general_messages": tuple(
                    sorted(message.code for message in general_messages)
                ),
                "pure": (
                    outcome.status.value,
                    outcome.whole_axis,
                    outcome.representative_width,
                    outcome.diagnostic_code,
                ),
                "formal": tuple(
                    (
                        member.start,
                        member.end,
                        member.from_waler,
                        member.to_waler,
                        member.recognition_method,
                    )
                    for member in members
                ),
                "result_messages": tuple(
                    sorted(
                        message.code
                        for message in result.messages
                        if source_handle in message.source_handles
                    )
                ),
            }
        )
    return tuple(sorted(records, key=lambda item: item["source_handle"]))


def _y05_s2_recognition_source():
    rail_intervals = (
        (
            -53475.5,
            (
                (9450.0, 8217.132034355973),
                (7792.86796564405, 7187.632034355962),
                (6763.367965644038, 6017.132034355968),
                (5592.867965644036, 3817.13203435597),
                (3392.867965644046, -3391.867965647673),
                (-3816.132034359598, -5591.867965647687),
                (-6016.13203435962, -6763.367965644291),
                (-7187.632034356213, -7791.867965647719),
                (-8216.132034359653, -9450.0),
            ),
            True,
        ),
        (
            -53463.5,
            (
                (9450.0, 8229.132034355978),
                (7804.867965644045, 7175.632034355966),
                (6751.367965644034, 6029.132034355964),
                (5604.867965644031, 3829.132034355966),
                (3404.867965644042, -3403.867965647669),
                (-3828.132034359602, -5601.85118105857),
                (-6028.132034359614, -6751.367965644294),
                (-7175.632034356211, -7803.867965647714),
                (-8228.132034359647, -9450.0),
            ),
            True,
        ),
        (
            -53294.5,
            (
                (9450.0, 8398.132034355971),
                (7973.867965644048, 7006.632034355964),
                (6582.36796564404, 6198.132034355966),
                (5773.867965644034, 3998.132034355968),
                (3573.867965644044, -3572.867965647672),
                (-3997.132034359595, -5772.867965647684),
                (-6197.132034359617, -6582.367965644291),
                (-7006.632034356215, -7972.867965647717),
                (-8397.132034359653, -9450.0),
            ),
            False,
        ),
        (
            -53644.5,
            (
                (9450.0, 8048.132034355971),
                (7623.867965644047, 7356.632034355965),
                (6932.367965644033, 5848.132034355966),
                (5423.867965644034, 3648.132034355967),
                (3223.867965644044, -3222.867965647671),
                (-3647.132034359595, -5422.867965647686),
                (-5847.132034359617, -6932.367965644283),
                (-7356.632034356207, -7622.867965647716),
                (-8047.132034359647, -9450.0),
            ),
            False,
        ),
    )
    primitives = []
    for x_coordinate, intervals, duplicated in rail_intervals:
        for start_y, end_y in intervals:
            primitives.append(
                BlockMemberPrimitive(
                    ((x_coordinate, start_y), (x_coordinate, end_y)),
                    False,
                    "LINE",
                    source_handle="957",
                )
            )
        if duplicated:
            for start_y, end_y in reversed(intervals):
                primitives.append(
                    BlockMemberPrimitive(
                        ((x_coordinate, end_y), (x_coordinate, start_y)),
                        False,
                        "LINE",
                        source_handle="957",
                    )
                )
    return BlockMemberRecognitionInput(
        root_handle="957",
        root_entity_type="INSERT",
        role="strut",
        primitives=tuple(primitives),
    )


def _y05_s10_recognition_source():
    """Return the WCS-equivalent primitives from Y05 root INSERT D17."""

    start_y = -23550.05
    end_y = 8450.0
    return BlockMemberRecognitionInput(
        root_handle="D17",
        root_entity_type="INSERT",
        role="strut",
        primitives=(
            BlockMemberPrimitive(
                ((-15504.5, end_y), (-15504.5, start_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15492.5, end_y), (-15492.5, start_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15492.5, start_y), (-15492.5, end_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15504.5, start_y), (-15504.5, end_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15323.5, start_y), (-15673.5, start_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15673.5, end_y), (-15323.5, end_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15323.5, end_y), (-15323.5, start_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
            BlockMemberPrimitive(
                ((-15673.5, end_y), (-15673.5, start_y)),
                False,
                "LINE",
                source_handle="D17",
            ),
        ),
    )


def _group_from_recognition_source(source):
    return _GeometryGroup(
        key=f"{source.role}:{source.root_handle}",
        role=source.role,
        layer=STRUT_LAYER,
        primitives=[
            _Primitive(
                list(primitive.points),
                primitive.closed,
                primitive.entity_type,
                source.root_handle,
                primitive.source_width,
            )
            for primitive in source.primitives
        ],
        handles={source.root_handle},
        entity_types={
            source.root_entity_type,
            *(primitive.entity_type for primitive in source.primitives),
        },
        block_instances=[],
        root_handle=source.root_handle,
        root_entity_type=source.root_entity_type,
    )


def _recognition_source_from_group(group):
    return BlockMemberRecognitionInput(
        root_handle=str(group.root_handle),
        root_entity_type=str(group.root_entity_type),
        role=str(group.role),
        primitives=tuple(
            BlockMemberPrimitive(
                tuple(primitive.points),
                primitive.closed,
                primitive.entity_type,
                primitive.source_handle,
                primitive.source_width,
            )
            for primitive in group.primitives
        ),
    )


def _convert_document(document, *, material_specs=()):
    importer = DXFImporter("synthetic-bim-block.dxf")
    importer._document = document
    importer._source_fingerprint = "synthetic-bim-block-fingerprint"
    return importer.convert(
        layer_roles={
            STRUT_LAYER: "strut",
            BRACE_LAYER: "brace",
            WALER_LAYER: "waler",
        },
        material_specs=material_specs,
    )


def _add_horizontal_strut_walers(document, *, start_x=0.0, end_x=12000.0):
    modelspace = document.modelspace()
    modelspace.add_line(
        (start_x, -1000.0),
        (start_x, 1000.0),
        dxfattribs={"layer": WALER_LAYER},
    )
    modelspace.add_line(
        (end_x, -1000.0),
        (end_x, 1000.0),
        dxfattribs={"layer": WALER_LAYER},
    )


def _add_y05_s2_insert(document):
    block = document.blocks.new("Y05_S2_ROOT_957_EQUIVALENT")
    for primitive in _y05_s2_recognition_source().primitives:
        block.add_line(primitive.points[0], primitive.points[1])
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_y05_s2_walers(document):
    modelspace = document.modelspace()
    for y_coordinate in (-9450.0, 9450.0):
        modelspace.add_line(
            (-54500.0, y_coordinate),
            (-52500.0, y_coordinate),
            dxfattribs={"layer": WALER_LAYER},
        )


def _add_y05_s10_insert(document):
    block = document.blocks.new("Y05_S10_ROOT_D17_EQUIVALENT")
    for primitive in _y05_s10_recognition_source().primitives:
        block.add_line(primitive.points[0], primitive.points[1])
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_y05_s10_walers(document):
    modelspace = document.modelspace()
    for y_coordinate in (-23550.05, 8450.0):
        modelspace.add_line(
            (-16500.0, y_coordinate),
            (-14500.0, y_coordinate),
            dxfattribs={"layer": WALER_LAYER},
        )


def _add_topology_conflict_insert(document):
    block = document.blocks.new("CONFLICTING_TOPOLOGY_STRUT")
    for center_y in (-150.0, 150.0):
        block.add_lwpolyline(
            (
                (0.0, center_y - 100.0),
                (12000.0, center_y - 100.0),
                (12000.0, center_y + 100.0),
                (0.0, center_y + 100.0),
            ),
            close=True,
        )
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_ambiguous_strut_insert(document):
    block = document.blocks.new("AMBIGUOUS_BIM_STRUT")
    horizontal_points = []
    for start, end in ((0.0, 2500.0), (9500.0, 12000.0)):
        points = (
            (start, -200.0),
            (end, -200.0),
            (end, 200.0),
            (start, 200.0),
        )
        horizontal_points.append(points)
        block.add_lwpolyline(points, close=True)
    for points in horizontal_points:
        block.add_lwpolyline(tuple((y, -x) for x, y in points), close=True)
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_ambiguous_brace_insert(document):
    block = document.blocks.new("AMBIGUOUS_BIM_BRACE")
    horizontal_points = []
    for start, end in ((0.0, 2500.0), (9500.0, 12000.0)):
        points = (
            (start, -150.0),
            (end, -150.0),
            (end, 150.0),
            (start, 150.0),
        )
        horizontal_points.append(points)
        block.add_lwpolyline(points, close=True)
    for points in horizontal_points:
        block.add_lwpolyline(tuple((y, -x) for x, y in points), close=True)
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": BRACE_LAYER},
    )


def _add_unreliable_extent_strut_insert(document):
    block = document.blocks.new("UNRELIABLE_EXTENT_BIM_STRUT")
    block.add_line((4500.0, -200.0), (7500.0, -200.0))
    block.add_line((4500.0, 200.0), (7500.0, 200.0))
    block.add_line((0.0, -40.0), (0.0, 40.0))
    block.add_line((12000.0, -40.0), (12000.0, 40.0))
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": STRUT_LAYER},
    )


def _add_unreliable_extent_brace_insert(document):
    block = document.blocks.new("UNRELIABLE_EXTENT_BIM_BRACE")
    block.add_line((4500.0, -150.0), (7500.0, -150.0))
    block.add_line((4500.0, 150.0), (7500.0, 150.0))
    block.add_line((0.0, -40.0), (0.0, 40.0))
    block.add_line((12000.0, -40.0), (12000.0, 40.0))
    return document.modelspace().add_blockref(
        block.name,
        (0.0, 0.0),
        dxfattribs={"layer": BRACE_LAYER},
    )


def _add_walers_at_axis(document, axis):
    start, end = axis
    delta_x = end[0] - start[0]
    delta_y = end[1] - start[1]
    axis_length = math.hypot(delta_x, delta_y)
    normal = -delta_y / axis_length, delta_x / axis_length
    for point in (start, end):
        document.modelspace().add_line(
            (
                point[0] - normal[0] * 1000.0,
                point[1] - normal[1] * 1000.0,
            ),
            (
                point[0] + normal[0] * 1000.0,
                point[1] + normal[1] * 1000.0,
            ),
            dxfattribs={"layer": WALER_LAYER},
        )


def _add_nested_fragmented_strut_insert(
    document,
    *,
    xscale,
    yscale,
    root_rotation,
    child_ocs=False,
    role="strut",
):
    suffix = f"{len(document.blocks)}"
    leaf = document.blocks.new(f"NESTED_{role.upper()}_FRAGMENT_LEAF_{suffix}")
    extrusion = (0.0, 0.0, -1.0) if child_ocs else (0.0, 0.0, 1.0)
    for start, end in (
        (0.0, 2200.0),
        (3100.0, 5200.0),
        (6800.0, 8900.0),
        (10100.0, 12000.0),
    ):
        leaf.add_lwpolyline(
            (
                (start, -200.0),
                (end, -200.0),
                (end, 200.0),
                (start, 200.0),
            ),
            close=True,
            dxfattribs={"extrusion": extrusion},
        )
    parent = document.blocks.new(f"NESTED_{role.upper()}_FRAGMENT_PARENT_{suffix}")
    child_insert = parent.add_blockref(
        leaf.name,
        (250.0, 100.0),
        dxfattribs={
            "rotation": 15.0,
            "xscale": 1.0,
            "yscale": 1.0,
        },
    )
    root_insert = document.modelspace().add_blockref(
        parent.name,
        (5000.0, -3000.0),
        dxfattribs={
            "layer": BRACE_LAYER if role == "brace" else STRUT_LAYER,
            "rotation": root_rotation,
            "xscale": xscale,
            "yscale": yscale,
        },
    )

    local_end_x = -12000.0 if child_ocs else 12000.0

    def to_world(point):
        child_point = child_insert.matrix44().transform((*point, 0.0))
        world_point = root_insert.matrix44().transform(child_point)
        return float(world_point.x), float(world_point.y)

    expected_axis = tuple(
        sorted((to_world((0.0, 0.0)), to_world((local_end_x, 0.0))))
    )
    _add_walers_at_axis(document, expected_axis)
    return root_insert, expected_axis


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF test asset unavailable")
class Y05BraceSourceCharacterizationTests(unittest.TestCase):
    legacy_expected_handles = {
        "9A7", "9C5", "9D7", "9E9", "A07", "A25", "A37", "A49",
        "B54", "B74", "B88", "B9C", "BBA", "BD8", "BEA", "D90",
        "DAC", "DC9", "DD9", "DE9", "E05", "E21", "E3E", "E4E",
        "E5E",
    }
    reuploaded_expected_handles = legacy_expected_handles | {"BFC"}
    current_expected_handles = {
        "1CC9", "1CCA", "1CCB", "1CCC", "1CCD", "1CCE", "1CCF", "1CD0",
        "1CE4", "1CE5", "1CE6", "1CE7", "1CE8", "1CE9", "1CEA", "1D07",
        "1D08", "1D09", "1D0A", "1D0B", "1D0C", "1D0D", "1D0E", "1D0F",
        "1D10", "2045",
    }

    @staticmethod
    def _known_fixture(records, legacy_handle, current_handle):
        return records[
            legacy_handle if legacy_handle in records else current_handle
        ]

    def test_characterization_is_deterministic_and_uses_exact_root_handles(self):
        first = _y05_brace_characterization()
        second = _y05_brace_characterization()

        self.assertEqual(second, first)
        self.assertIn(
            {record["source_handle"] for record in first},
            (
                self.legacy_expected_handles,
                self.reuploaded_expected_handles,
                self.current_expected_handles,
            ),
        )
        self.assertTrue(
            all(record["root_entity_type"] == "INSERT" for record in first)
        )
        self.assertTrue(all(record["primitive_count"] > 0 for record in first))
        self.assertTrue(
            all(
                record["pure"][0]
                in {"not_applicable", "recognized", "failed", "ambiguous"}
                for record in first
            )
        )

    def test_characterization_separates_general_pure_and_connection_outcomes(self):
        records = {
            record["source_handle"]: record
            for record in _y05_brace_characterization()
        }

        a37 = self._known_fixture(records, "A37", "1CCF")
        self.assertEqual(a37["general"][0], "parallel_edges_midline")
        self.assertEqual(a37["pure"][0], "recognized")
        general_length = math.dist(a37["general"][1], a37["general"][2])
        whole_length = math.dist(*a37["pure"][1])
        self.assertGreater(whole_length, general_length)
        self.assertEqual(len(a37["formal"]), 1)
        self.assertEqual(a37["formal"][0][4], "bim_block_whole_axis")
        self.assertEqual(
            a37["result_messages"].count("BRACE_AXIS_EXTENDED_TO_WALER"),
            2,
        )

        de9 = self._known_fixture(records, "DE9", "1D0B")
        self.assertIsNone(de9["general"])
        self.assertEqual(de9["pure"][0], "recognized")
        self.assertEqual(len(de9["formal"]), 1)
        self.assertEqual(de9["formal"][0][4], "bim_block_whole_axis")
        self.assertNotIn("BRACE_RECOGNITION_FAILED", de9["result_messages"])
        if "BRACE_NOT_CONNECTED" in de9["result_messages"]:
            self.assertEqual(de9["formal"][0][2:4], ("", ""))
            self.assertEqual(de9["formal"][0][:2], de9["pure"][1])
        else:
            # The reuploaded Y05 source includes the W13/W14 context needed
            # to finalize this already-recognized Brace axis.
            self.assertEqual(de9["formal"][0][2:4], ("W14", "W13"))

        b9c = self._known_fixture(records, "B9C", "1CE7")
        self.assertEqual(b9c["pure"][0], "recognized")
        self.assertEqual(len(b9c["formal"]), 1)
        self.assertEqual(b9c["formal"][0][4], "bim_block_whole_axis")
        self.assertEqual(b9c["formal"][0][2:4], ("W5", "W4"))
        self.assertEqual(
            b9c["result_messages"].count("BRACE_AXIS_EXTENDED_TO_WALER"),
            1,
        )
        self.assertNotIn("BRACE_ONE_END_NOT_CONNECTED", b9c["result_messages"])

    def test_selected_y05_root_fixtures_have_distinct_expected_outcomes(self):
        records = {
            record["source_handle"]: record
            for record in _y05_brace_characterization()
        }

        shortened = self._known_fixture(records, "A37", "1CCF")
        self.assertEqual(shortened["general"][0], "parallel_edges_midline")
        self.assertEqual(shortened["pure"][0], "recognized")
        self.assertGreater(
            math.dist(*shortened["pure"][1]),
            math.dist(shortened["general"][1], shortened["general"][2]),
        )

        completed_connection = self._known_fixture(records, "B9C", "1CE7")
        self.assertEqual(completed_connection["pure"][0], "recognized")
        self.assertEqual(completed_connection["formal"][0][2:4], ("W5", "W4"))
        self.assertNotIn(
            "BRACE_ONE_END_NOT_CONNECTED",
            completed_connection["result_messages"],
        )

    def test_y05_9e9_extends_both_source_supported_endpoints_to_w1_and_w2(self):
        records = {
            item["source_handle"]: item
            for item in _y05_brace_characterization()
        }
        record = self._known_fixture(records, "9E9", "1CCC")
        member = record["formal"][0]
        self.assertEqual(member[2:4], ("W1", "W2"))
        extension_distances = tuple(
            math.dist(source, adopted)
            for source, adopted in zip(record["pure"][1], member[:2])
        )
        self.assertAlmostEqual(extension_distances[0], 425.205551, places=3)
        self.assertAlmostEqual(extension_distances[1], 425.205551, places=3)
        self.assertEqual(
            record["result_messages"].count("BRACE_AXIS_EXTENDED_TO_WALER"),
            2,
        )
        self.assertNotIn("BRACE_NOT_CONNECTED", record["result_messages"])

    def test_y05_b9c_keeps_w4_direct_end_and_extends_other_end_to_w5(self):
        records = {
            item["source_handle"]: item
            for item in _y05_brace_characterization()
        }
        record = self._known_fixture(records, "B9C", "1CE7")
        member = record["formal"][0]
        self.assertEqual(member[2:4], ("W5", "W4"))
        endpoint_movements = tuple(
            math.dist(source, adopted)
            for source, adopted in zip(record["pure"][1], member[:2])
        )
        self.assertAlmostEqual(endpoint_movements[0], 502.705551, places=3)
        self.assertLessEqual(
            endpoint_movements[1],
            GeometryTolerances().connection_tolerance_mm,
        )
        self.assertGreater(
            endpoint_movements[0],
            GeometryTolerances().connection_tolerance_mm,
        )
        self.assertEqual(
            record["result_messages"].count("BRACE_AXIS_EXTENDED_TO_WALER"),
            1,
        )
        self.assertNotIn("BRACE_ONE_END_NOT_CONNECTED", record["result_messages"])


class BIMBlockRootGroupingCharacterizationTests(unittest.TestCase):
    def assert_root_provenance(self, group, source_geometry, root_handle):
        self.assertEqual(group.root_handle, root_handle)
        self.assertEqual(group.root_entity_type, "INSERT")
        self.assertEqual(group.handles, {root_handle})
        self.assertEqual(
            {primitive.source_handle for primitive in group.primitives},
            {root_handle},
        )
        self.assertEqual(
            {geometry.source_handle for geometry in source_geometry},
            {root_handle},
        )
        self.assertEqual(group.block_instances[0].handle, root_handle)

    def test_ordinary_insert_is_one_root_group_with_root_provenance(self):
        document = _new_document()
        insert = _add_ordinary_insert(document)

        groups, source_geometry = _extract_strut_groups(document)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].primitives), 1)
        self.assertEqual(groups[0].entity_types, {"INSERT", "LINE"})
        self.assert_root_provenance(groups[0], source_geometry, insert.dxf.handle)

    def test_complete_outline_insert_is_one_root_group(self):
        document = _new_document()
        insert = _add_complete_outline_insert(document)

        groups, source_geometry = _extract_strut_groups(document)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].primitives), 1)
        self.assertTrue(groups[0].primitives[0].closed)
        self.assertEqual(groups[0].entity_types, {"INSERT", "LWPOLYLINE"})
        self.assert_root_provenance(groups[0], source_geometry, insert.dxf.handle)

    def test_fragmented_insert_keeps_all_rectangles_in_one_root_group(self):
        document = _new_document()
        insert = _add_fragmented_strut_insert(document)

        groups, source_geometry = _extract_strut_groups(document)

        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].primitives), 4)
        self.assertTrue(all(item.closed for item in groups[0].primitives))
        self.assertEqual(len(source_geometry), 4)
        self.assert_root_provenance(groups[0], source_geometry, insert.dxf.handle)


class BIMBlockRootLayerCharacterizationTests(unittest.TestCase):
    def test_layer_zero_children_keep_the_root_strut_role(self):
        document = _new_document()
        insert = _add_single_line_insert(
            document,
            block_name="LAYER_ZERO_STRUT",
            root_layer=STRUT_LAYER,
        )

        groups, source_geometry = _extract_strut_groups(document)

        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].role, "strut")
        self.assertEqual(groups[0].layer, STRUT_LAYER)
        self.assertEqual(groups[0].root_handle, insert.dxf.handle)
        self.assertEqual(groups[0].root_entity_type, "INSERT")
        self.assertEqual(source_geometry[0].role, "strut")
        self.assertEqual(source_geometry[0].source_layer, STRUT_LAYER)

    def test_brace_and_waler_root_layers_keep_existing_recognition_path(self):
        document = _new_document()
        _add_single_line_insert(
            document,
            block_name="LAYER_ZERO_BRACE",
            root_layer=BRACE_LAYER,
        )
        _add_single_line_insert(
            document,
            block_name="LAYER_ZERO_WALER",
            root_layer=WALER_LAYER,
        )

        for role, layer in (("brace", BRACE_LAYER), ("waler", WALER_LAYER)):
            with self.subTest(role=role):
                groups, source_geometry = _extract_groups(
                    document,
                    role=role,
                    layer=layer,
                )
                candidate, messages = _candidate_from_group(
                    groups[0],
                    role,
                    GeometryTolerances(),
                )

                self.assertEqual(groups[0].role, role)
                self.assertEqual(source_geometry[0].role, role)
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate.recognition_method, "existing_centerline")
                self.assertEqual(messages, [])


class BIMBlockRecognitionRouterTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def group_from_primitives(
        primitives,
        *,
        role="strut",
        root_handle="ROOT-1",
        root_entity_type="INSERT",
    ):
        return _GeometryGroup(
            key=f"{role}:{root_handle}",
            role=role,
            layer=STRUT_LAYER if role == "strut" else BRACE_LAYER,
            primitives=[
                _Primitive(
                    list(primitive.points),
                    primitive.closed,
                    primitive.entity_type,
                    root_handle,
                    primitive.source_width,
                )
                for primitive in primitives
            ],
            handles={root_handle} if root_handle else set(),
            entity_types={root_entity_type, *(item.entity_type for item in primitives)},
            block_instances=[],
            root_handle=root_handle or None,
            root_entity_type=root_entity_type,
        )

    @staticmethod
    def rectangle(start, end, *, center_y=0.0):
        return BlockMemberPrimitive(
            (
                (start, center_y - 200.0),
                (end, center_y - 200.0),
                (end, center_y + 200.0),
                (start, center_y + 200.0),
            ),
            True,
            "LWPOLYLINE",
        )

    @classmethod
    def fragmented_primitives(cls):
        return tuple(
            cls.rectangle(start, end)
            for start, end in (
                (0.0, 2200.0),
                (3100.0, 5200.0),
                (6800.0, 8900.0),
                (10100.0, 12000.0),
            )
        )

    def test_router_only_calls_service_for_strut_root_insert_with_handle(self):
        primitive = BlockMemberPrimitive(
            ((0.0, 0.0), (12000.0, 0.0)),
            False,
            "LINE",
        )
        cases = (
            *(
                self.group_from_primitives((primitive,), role=role)
                for role in (
                    "brace",
                    "waler",
                    "continuous_wall",
                    "column",
                    "beam",
                    "corner_brace",
                )
            ),
            self.group_from_primitives(
                (primitive,),
                root_entity_type="LINE",
            ),
            self.group_from_primitives((primitive,), root_handle=""),
        )

        with patch(
            "dxf_import.recognition.recognize_component_like_strut"
        ) as recognize:
            results = tuple(
                _route_component_like_strut_block(group, self.tolerances)
                for group in cases
            )

        self.assertTrue(all(not result.handled for result in results))
        recognize.assert_not_called()

    def test_role_aware_router_accepts_only_strut_and_brace_root_inserts(self):
        primitive = BlockMemberPrimitive(
            ((0.0, 0.0), (12000.0, 0.0)),
            False,
            "LINE",
        )
        supported = tuple(
            self.group_from_primitives((primitive,), role=role)
            for role in ("strut", "brace")
        )
        unsupported = tuple(
            self.group_from_primitives((primitive,), role=role)
            for role in (
                "waler",
                "continuous_wall",
                "column",
                "beam",
                "corner_brace",
            )
        )

        supported_results = tuple(
            _route_component_like_member_block(group, self.tolerances)
            for group in supported
        )
        unsupported_results = tuple(
            _route_component_like_member_block(group, self.tolerances)
            for group in unsupported
        )

        self.assertTrue(all(not result.handled for result in supported_results))
        self.assertTrue(all(not result.handled for result in unsupported_results))

    def test_not_applicable_keeps_same_root_group_for_general_recognition(self):
        primitive = BlockMemberPrimitive(
            ((0.0, 0.0), (12000.0, 0.0)),
            False,
            "LINE",
        )
        group = self.group_from_primitives((primitive,))

        route = _route_component_like_strut_block(group, self.tolerances)
        candidate, messages = _candidate_from_group(
            group,
            "strut",
            self.tolerances,
        )

        self.assertFalse(route.handled)
        self.assertIsNone(route.candidate)
        self.assertEqual(route.messages, ())
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.recognition_method, "existing_centerline")
        self.assertEqual(candidate.handles, {"ROOT-1"})
        self.assertEqual(messages, [])

    def test_each_fragmented_root_insert_is_routed_independently(self):
        document = _new_document()
        first = _add_fragmented_strut_insert(document)
        second = document.modelspace().add_blockref(
            "FRAGMENTED_STRUT",
            (15000.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )
        groups, _source_geometry = _extract_strut_groups(document)

        routes = tuple(
            _route_component_like_strut_block(group, self.tolerances)
            for group in groups
        )

        self.assertEqual(len(routes), 2)
        self.assertTrue(all(result.handled for result in routes))
        self.assertTrue(all(result.candidate is not None for result in routes))
        self.assertEqual(
            {next(iter(result.candidate.handles)) for result in routes},
            {first.dxf.handle, second.dxf.handle},
        )

    def test_terminal_ambiguity_is_handled_without_general_fallback(self):
        horizontal = (
            self.rectangle(0.0, 2500.0),
            self.rectangle(9500.0, 12000.0),
        )
        vertical = tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in horizontal
        )
        group = self.group_from_primitives(horizontal + vertical)

        route = _route_component_like_strut_block(group, self.tolerances)

        self.assertTrue(route.handled)
        self.assertIsNone(route.candidate)
        self.assertEqual(len(route.messages), 1)
        self.assertEqual(
            route.messages[0].code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )
        self.assertEqual(route.messages[0].source_handles, ("ROOT-1",))

    def test_brace_terminal_ambiguity_is_role_correct_and_blocks_fallback(self):
        horizontal = (
            self.rectangle(0.0, 2500.0),
            self.rectangle(9500.0, 12000.0),
        )
        vertical = tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in horizontal
        )
        group = self.group_from_primitives(
            horizontal + vertical,
            role="brace",
            root_handle="BRACE-CONFLICT-ROOT",
        )

        route = _route_component_like_member_block(group, self.tolerances)

        self.assertTrue(route.handled)
        self.assertIsNone(route.candidate)
        self.assertEqual(len(route.messages), 1)
        message = route.messages[0]
        self.assertEqual(message.code, "BIM_BLOCK_CONFLICTING_WHOLE_AXES")
        self.assertEqual(message.role, "brace")
        self.assertEqual(message.source_handles, ("BRACE-CONFLICT-ROOT",))
        self.assertIn("斜撐", message.message)
        self.assertNotIn("支撐構件", message.message)

    def test_brace_not_applicable_returns_same_root_to_general_recognition(self):
        primitive = BlockMemberPrimitive(
            ((0.0, 0.0), (12000.0, 0.0)),
            False,
            "LINE",
        )
        group = self.group_from_primitives(
            (primitive,),
            role="brace",
            root_handle="ORDINARY-BRACE-ROOT",
        )

        route = _route_component_like_member_block(group, self.tolerances)
        candidate, messages = _candidate_from_group(
            group,
            "brace",
            self.tolerances,
        )

        self.assertFalse(route.handled)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.handles, {"ORDINARY-BRACE-ROOT"})
        self.assertEqual(candidate.recognition_method, "existing_centerline")
        self.assertEqual(messages, [])

    def test_fragmented_brace_root_maps_to_one_role_correct_candidate(self):
        group = self.group_from_primitives(
            self.fragmented_primitives(),
            role="brace",
            root_handle="FRAGMENTED-BRACE-ROOT",
        )

        route = _route_component_like_member_block(group, self.tolerances)

        self.assertTrue(route.handled)
        self.assertIsNotNone(route.candidate)
        self.assertEqual(route.candidate.handles, {"FRAGMENTED-BRACE-ROOT"})
        self.assertEqual(
            route.candidate.recognition_method,
            "bim_block_whole_axis",
        )
        self.assertEqual(route.candidate.start, (0.0, 0.0))
        self.assertEqual(route.candidate.end, (12000.0, 0.0))
        self.assertEqual(route.messages, ())

    def test_y05_s10_topology_result_is_terminal_before_general_fallback(self):
        source = _y05_s10_recognition_source()
        group = _group_from_recognition_source(source)

        route = _route_component_like_strut_block(group, self.tolerances)
        legacy_candidate, legacy_messages = _candidate_from_group(
            group,
            "strut",
            self.tolerances,
        )

        self.assertTrue(route.handled)
        self.assertIsNotNone(route.candidate)
        self.assertEqual(route.candidate.handles, {"D17"})
        self.assertEqual(route.candidate.recognition_method, "bim_block_whole_axis")
        self.assertAlmostEqual(route.candidate.start[0], -15498.5)
        self.assertAlmostEqual(route.candidate.end[0], -15498.5)
        self.assertAlmostEqual(route.candidate.source_width, 350.0)
        self.assertEqual(route.messages, ())
        self.assertAlmostEqual(legacy_candidate.start[0], -15414.0)
        self.assertEqual(
            {message.code for message in legacy_messages},
            {"AMBIGUOUS_CENTERLINE"},
        )

    def test_line_group_merge_never_crosses_root_insert_boundaries(self):
        document = _new_document()
        block = document.blocks.new("ONE_LINE_ROOT")
        block.add_line((0.0, 0.0), (1000.0, 0.0))
        first = document.modelspace().add_blockref(
            block.name,
            (0.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )
        second = document.modelspace().add_blockref(
            block.name,
            (1000.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )
        groups, _source_geometry = _extract_strut_groups(document)

        merged = DXFImporter._merge_related_line_groups(
            groups,
            self.tolerances,
        )

        self.assertEqual(len(merged), 2)
        self.assertEqual(
            {group.root_handle for group in merged},
            {first.dxf.handle, second.dxf.handle},
        )

    def test_standalone_line_bypasses_bim_and_keeps_existing_centerline(self):
        primitive = BlockMemberPrimitive(
            ((0.0, 0.0), (12000.0, 0.0)),
            False,
            "LINE",
        )
        group = self.group_from_primitives(
            (primitive,),
            root_entity_type="LINE",
        )

        with patch(
            "dxf_import.recognition.recognize_component_like_strut"
        ) as recognize:
            route = _route_component_like_strut_block(group, self.tolerances)
        candidate, messages = _candidate_from_group(
            group,
            "strut",
            self.tolerances,
        )

        self.assertFalse(route.handled)
        recognize.assert_not_called()
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.recognition_method, "existing_centerline")
        self.assertEqual(messages, [])

    def test_small_endpoint_gaps_keep_existing_line_group_recognition(self):
        points = (
            ((25.0, -200.0), (11975.0, -200.0)),
            ((12000.0, -175.0), (12000.0, 175.0)),
            ((11975.0, 200.0), (25.0, 200.0)),
            ((0.0, 175.0), (0.0, -175.0)),
        )
        groups = [
            self.group_from_primitives(
                (
                    BlockMemberPrimitive(
                        segment,
                        False,
                        "LINE",
                    ),
                ),
                root_handle=f"LINE-{index}",
                root_entity_type="LINE",
            )
            for index, segment in enumerate(points)
        ]

        merged = DXFImporter._merge_related_line_groups(groups, self.tolerances)
        candidate, messages = _candidate_from_group(
            merged[0],
            "strut",
            self.tolerances,
        )

        self.assertEqual(len(merged), 1)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.recognition_method, "parallel_edges_midline")
        self.assertEqual(candidate.start, (25.0, 0.0))
        self.assertEqual(candidate.end, (11975.0, 0.0))
        self.assertEqual(messages, [])


class BIMBlockCandidateIntegrationTests(unittest.TestCase):
    def test_fragmented_brace_root_creates_one_formal_brace(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_brace_insert(document)

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 1)
        member = result.braces[0]
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.start, (0.0, 0.0))
        self.assertEqual(member.end, (12000.0, 0.0))
        self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))
        self.assertFalse(
            {
                "BRACE_ONE_END_NOT_CONNECTED",
                "BRACE_NOT_CONNECTED",
            }.intersection(message.code for message in result.messages)
        )

    def test_recognized_brace_with_one_waler_keeps_axis_and_connection_error(self):
        document = _new_document()
        document.modelspace().add_line(
            (0.0, -1000.0),
            (0.0, 1000.0),
            dxfattribs={"layer": WALER_LAYER},
        )
        _add_fragmented_brace_insert(document)

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 1)
        member = result.braces[0]
        self.assertEqual((member.start, member.end), ((0.0, 0.0), (12000.0, 0.0)))
        self.assertEqual(member.from_waler, "W1")
        self.assertEqual(member.to_waler, "")
        self.assertIn(
            "BRACE_ONE_END_NOT_CONNECTED",
            {message.code for message in result.messages},
        )

    def test_recognized_brace_without_walers_keeps_axis_and_connection_error(self):
        document = _new_document()
        _add_fragmented_brace_insert(document)

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 1)
        member = result.braces[0]
        self.assertEqual((member.start, member.end), ((0.0, 0.0), (12000.0, 0.0)))
        self.assertEqual((member.from_waler, member.to_waler), ("", ""))
        self.assertIn(
            "BRACE_NOT_CONNECTED",
            {message.code for message in result.messages},
        )

    def test_waler_context_does_not_choose_or_extend_brace_geometry(self):
        axes = []
        connection_codes = []
        for connected_end_count in (0, 1, 2):
            document = _new_document()
            _add_fragmented_brace_insert(document)
            if connected_end_count >= 1:
                document.modelspace().add_line(
                    (0.0, -1000.0),
                    (0.0, 1000.0),
                    dxfattribs={"layer": WALER_LAYER},
                )
            if connected_end_count == 2:
                document.modelspace().add_line(
                    (12000.0, -1000.0),
                    (12000.0, 1000.0),
                    dxfattribs={"layer": WALER_LAYER},
                )

            result = _convert_document(document)
            member = result.braces[0]
            axes.append((member.start, member.end, member.recognition_method))
            connection_codes.append(
                {
                    message.code
                    for message in result.messages
                    if message.code.startswith("BRACE_")
                }
            )

        self.assertEqual(
            axes,
            [
                ((0.0, 0.0), (12000.0, 0.0), "bim_block_whole_axis"),
            ]
            * 3,
        )
        self.assertIn("BRACE_NOT_CONNECTED", connection_codes[0])
        self.assertIn("BRACE_ONE_END_NOT_CONNECTED", connection_codes[1])
        self.assertFalse(
            {
                "BRACE_NOT_CONNECTED",
                "BRACE_ONE_END_NOT_CONNECTED",
            }.intersection(connection_codes[2])
        )

    def test_fragmented_brace_roots_are_not_merged_across_root_handles(self):
        document = _new_document()
        first = _add_fragmented_brace_insert(document)
        second = document.modelspace().add_blockref(
            "FRAGMENTED_BRACE",
            (15000.0, 0.0),
            dxfattribs={"layer": BRACE_LAYER},
        )
        _add_horizontal_strut_walers(document)
        _add_horizontal_strut_walers(
            document,
            start_x=15000.0,
            end_x=27000.0,
        )

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 2)
        self.assertEqual(
            {member.source_handles for member in result.braces},
            {(first.dxf.handle,), (second.dxf.handle,)},
        )
        self.assertEqual(
            {(member.start, member.end) for member in result.braces},
            {
                ((0.0, 0.0), (12000.0, 0.0)),
                ((15000.0, 0.0), (27000.0, 0.0)),
            },
        )

    def test_ambiguous_brace_root_creates_reviewable_problem_not_member(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_ambiguous_brace_insert(document)

        result = _convert_document(document)

        self.assertEqual(result.braces, ())
        messages = tuple(
            message
            for message in result.messages
            if message.code == "BIM_BLOCK_CONFLICTING_WHOLE_AXES"
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "brace")
        self.assertEqual(messages[0].source_handles, (insert.dxf.handle,))
        self.assertIn("斜撐", messages[0].message)
        self.assertNotIn("支撐構件", messages[0].message)
        review_items = tuple(
            item
            for item in build_review_items(result)
            if item.source_handles == (insert.dxf.handle,)
        )
        self.assertEqual(len(review_items), 1)
        self.assertEqual(review_items[0].role, "brace")
        self.assertEqual(review_items[0].status, "unresolved")

    def test_failed_brace_root_creates_reviewable_problem_not_member(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_unreliable_extent_brace_insert(document)

        result = _convert_document(document)

        self.assertEqual(result.braces, ())
        messages = tuple(
            message
            for message in result.messages
            if message.code == "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE"
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "brace")
        self.assertEqual(messages[0].source_handles, (insert.dxf.handle,))
        self.assertIn("斜撐", messages[0].message)
        self.assertNotIn("支撐構件", messages[0].message)
        review_items = tuple(
            item
            for item in build_review_items(result)
            if item.source_handles == (insert.dxf.handle,)
        )
        self.assertEqual(len(review_items), 1)
        self.assertEqual(review_items[0].role, "brace")
        self.assertEqual(review_items[0].status, "unresolved")

    def test_ordinary_brace_insert_keeps_general_recognition(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_single_line_insert(
            document,
            block_name="ORDINARY_BRACE",
            root_layer=BRACE_LAYER,
        )

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 1)
        self.assertEqual(result.braces[0].source_handles, (insert.dxf.handle,))
        self.assertEqual(
            result.braces[0].recognition_method,
            "existing_centerline",
        )

    def test_recognized_block_exposes_only_the_whole_axis_candidate(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_strut_insert(document)

        result = _convert_document(document)

        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assertTrue(member.centerline_computed)
        self.assertAlmostEqual(member.source_width, 400.0)
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.start, (0.0, 0.0))
        self.assertEqual(member.end, (12000.0, 0.0))
        self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))
        self.assertEqual(len(member.line_candidates), 1)
        self.assertEqual(
            member.line_candidates[0].source,
            "bim_block_whole_axis",
        )
        self.assertEqual(member.line_candidates[0].world_start, member.start)
        self.assertEqual(member.line_candidates[0].world_end, member.end)
        recommended_points = {
            point.id: point.world_point for point in member.candidate_points
        }
        self.assertEqual(
            recommended_points[member.recommended_start_point_id],
            member.start,
        )
        self.assertEqual(
            recommended_points[member.recommended_end_point_id],
            member.end,
        )


class BIMBlockNestedWCSIntegrationTests(unittest.TestCase):
    def assert_member_axis(self, member, expected_axis):
        for actual_point, expected_point in zip(
            (member.start, member.end),
            expected_axis,
        ):
            self.assertAlmostEqual(actual_point[0], expected_point[0], places=6)
            self.assertAlmostEqual(actual_point[1], expected_point[1], places=6)

    def test_nested_insert_applies_positive_and_negative_scale_once(self):
        cases = (
            (1.25, 1.25, 30.0),
            (-1.0, 1.0, 40.0),
        )
        for xscale, yscale, rotation in cases:
            with self.subTest(xscale=xscale, yscale=yscale, rotation=rotation):
                document = _new_document()
                root, expected_axis = _add_nested_fragmented_strut_insert(
                    document,
                    xscale=xscale,
                    yscale=yscale,
                    root_rotation=rotation,
                )

                result = _convert_document(document)

                self.assertEqual(len(result.struts), 1)
                member = result.struts[0]
                self.assertEqual(member.recognition_method, "bim_block_whole_axis")
                self.assertEqual(member.source_handles, (root.dxf.handle,))
                self.assert_member_axis(member, expected_axis)
                self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))
                self.assertTrue(
                    all(
                        geometry.source_handle == root.dxf.handle
                        for geometry in result.source_geometry
                        if geometry.role == "strut"
                    )
                )

    def test_nested_child_ocs_geometry_produces_the_expected_wcs_axis(self):
        document = _new_document()
        root, expected_axis = _add_nested_fragmented_strut_insert(
            document,
            xscale=1.0,
            yscale=1.0,
            root_rotation=25.0,
            child_ocs=True,
        )

        result = _convert_document(document)

        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.source_handles, (root.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assert_member_axis(member, expected_axis)
        strut_source = tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role == "strut"
        )
        self.assertEqual(len(strut_source), 4)
        self.assertEqual(
            {geometry.source_handle for geometry in strut_source},
            {root.dxf.handle},
        )

    def test_nested_brace_applies_rotation_and_scale_once(self):
        cases = (
            (1.25, 1.25, 30.0),
            (-1.0, 1.0, 40.0),
        )
        for xscale, yscale, rotation in cases:
            with self.subTest(xscale=xscale, yscale=yscale, rotation=rotation):
                document = _new_document()
                root, expected_axis = _add_nested_fragmented_strut_insert(
                    document,
                    xscale=xscale,
                    yscale=yscale,
                    root_rotation=rotation,
                    role="brace",
                )

                result = _convert_document(document)

                self.assertEqual(len(result.braces), 1)
                member = result.braces[0]
                self.assertEqual(member.recognition_method, "bim_block_whole_axis")
                self.assertEqual(member.source_handles, (root.dxf.handle,))
                self.assert_member_axis(member, expected_axis)
                self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))
                brace_source = tuple(
                    geometry
                    for geometry in result.source_geometry
                    if geometry.role == "brace"
                )
                self.assertEqual(len(brace_source), 4)
                self.assertEqual(
                    {geometry.source_handle for geometry in brace_source},
                    {root.dxf.handle},
                )

    def test_nested_brace_child_ocs_produces_expected_wcs_axis(self):
        document = _new_document()
        root, expected_axis = _add_nested_fragmented_strut_insert(
            document,
            xscale=1.0,
            yscale=1.0,
            root_rotation=25.0,
            child_ocs=True,
            role="brace",
        )

        result = _convert_document(document)

        self.assertEqual(len(result.braces), 1)
        member = result.braces[0]
        self.assertEqual(member.source_handles, (root.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assert_member_axis(member, expected_axis)
        brace_source = tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role == "brace"
        )
        self.assertEqual(len(brace_source), 4)
        self.assertEqual(
            {geometry.source_handle for geometry in brace_source},
            {root.dxf.handle},
        )


class BIMBlockImporterDeterminismTests(unittest.TestCase):
    intervals = (
        (0.0, 2200.0),
        (3100.0, 5200.0),
        (6800.0, 8900.0),
        (10100.0, 12000.0),
    )

    @staticmethod
    def rectangle_points(start, end):
        return [
            (start, -200.0),
            (end, -200.0),
            (end, 200.0),
            (start, 200.0),
        ]

    def success_document(self, variant):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        block = document.blocks.new(f"DETERMINISTIC_SUCCESS_{variant}")
        intervals = (
            tuple(reversed(self.intervals))
            if variant == "child_order"
            else self.intervals
        )
        for index, (start, end) in enumerate(intervals):
            points = self.rectangle_points(start, end)
            if variant == "polyline_traversal":
                offset = (index + 1) % len(points)
                points = points[offset:] + points[:offset]
                points.reverse()
            if variant == "line_direction":
                for point_index, point in enumerate(points):
                    next_point = points[(point_index + 1) % len(points)]
                    block.add_line(next_point, point)
            else:
                block.add_lwpolyline(points, close=True)
                if variant == "duplicates":
                    block.add_lwpolyline(tuple(reversed(points)), close=True)
        insert = document.modelspace().add_blockref(
            block.name,
            (0.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )
        return document, insert

    def test_success_permutations_preserve_whole_axis_and_root_provenance(self):
        outcomes = []
        for variant in (
            "base",
            "child_order",
            "line_direction",
            "polyline_traversal",
            "duplicates",
        ):
            with self.subTest(variant=variant):
                document, insert = self.success_document(variant)
                result = _convert_document(document)

                self.assertEqual(len(result.struts), 1)
                member = result.struts[0]
                self.assertEqual(member.source_handles, (insert.dxf.handle,))
                self.assertEqual(member.recognition_method, "bim_block_whole_axis")
                self.assertEqual(member.start, (0.0, 0.0))
                self.assertEqual(member.end, (12000.0, 0.0))
                outcomes.append(
                    (
                        member.start,
                        member.end,
                        member.source_width,
                        member.confidence,
                        member.recognition_method,
                    )
                )
        first = outcomes[0]
        for outcome in outcomes[1:]:
            self.assertEqual(outcome, first)

    def test_general_fallback_is_deterministic_when_line_direction_reverses(self):
        outcomes = []
        for reversed_line in (False, True):
            document = _new_document()
            _add_horizontal_strut_walers(document)
            block = document.blocks.new(f"FALLBACK_{reversed_line}")
            endpoints = ((0.0, 0.0), (12000.0, 0.0))
            if reversed_line:
                endpoints = tuple(reversed(endpoints))
            block.add_line(*endpoints)
            insert = document.modelspace().add_blockref(
                block.name,
                (0.0, 0.0),
                dxfattribs={"layer": STRUT_LAYER},
            )

            result = _convert_document(document)

            self.assertEqual(len(result.struts), 1)
            member = result.struts[0]
            self.assertEqual(member.source_handles, (insert.dxf.handle,))
            self.assertEqual(member.recognition_method, "existing_centerline")
            outcomes.append((member.start, member.end, member.recognition_method))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_ambiguity_is_deterministic_when_children_and_paths_are_reordered(self):
        outcomes = []
        for permuted in (False, True):
            document = _new_document()
            _add_horizontal_strut_walers(document)
            block = document.blocks.new(f"AMBIGUOUS_PERMUTED_{permuted}")
            horizontal = (
                self.rectangle_points(0.0, 2500.0),
                self.rectangle_points(9500.0, 12000.0),
            )
            primitives = list(horizontal) + [
                [(y, -x) for x, y in points]
                for points in horizontal
            ]
            if permuted:
                primitives.reverse()
            for index, points in enumerate(primitives):
                if permuted:
                    offset = (index + 1) % len(points)
                    points = points[offset:] + points[:offset]
                    points.reverse()
                block.add_lwpolyline(points, close=True)
            insert = document.modelspace().add_blockref(
                block.name,
                (0.0, 0.0),
                dxfattribs={"layer": STRUT_LAYER},
            )

            result = _convert_document(document)
            source_messages = tuple(
                message
                for message in result.messages
                if message.source_handles == (insert.dxf.handle,)
            )

            self.assertEqual(result.struts, ())
            self.assertEqual(len(source_messages), 1)
            self.assertEqual(
                source_messages[0].code,
                "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
            )
            outcomes.append((source_messages[0].code, source_messages[0].role))
        self.assertEqual(outcomes[0], outcomes[1])


class BIMBlockSourceGeometryIntegrationTests(unittest.TestCase):
    def test_recognition_keeps_fragment_underlay_and_never_merges_roots(self):
        document = _new_document()
        modelspace = document.modelspace()
        for x_coordinate in (0.0, 12000.0):
            modelspace.add_line(
                (x_coordinate, -1000.0),
                (x_coordinate, 4000.0),
                dxfattribs={"layer": WALER_LAYER},
            )
        first = _add_fragmented_strut_insert(document)
        second = modelspace.add_blockref(
            "FRAGMENTED_STRUT",
            (0.0, 3000.0),
            dxfattribs={"layer": STRUT_LAYER},
        )

        result = _convert_document(document)
        strut_geometry = tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role == "strut"
        )
        geometry_by_root = {
            handle: tuple(
                geometry
                for geometry in strut_geometry
                if geometry.source_handle == handle
            )
            for handle in (first.dxf.handle, second.dxf.handle)
        }

        self.assertEqual(len(result.struts), 2)
        self.assertEqual(
            {member.source_handles for member in result.struts},
            {(first.dxf.handle,), (second.dxf.handle,)},
        )
        self.assertEqual(len(strut_geometry), 8)
        for handle, geometries in geometry_by_root.items():
            with self.subTest(root_handle=handle):
                self.assertEqual(len(geometries), 4)
                self.assertTrue(all(geometry.closed for geometry in geometries))
                self.assertTrue(all(len(geometry.points) == 4 for geometry in geometries))
                self.assertEqual(
                    {geometry.source_handle for geometry in geometries},
                    {handle},
                )
        self.assertFalse(
            any(len(geometry.points) == 2 for geometry in strut_geometry)
        )


class BIMBlockProblemIntegrationTests(unittest.TestCase):
    def assert_terminal_source_problem(
        self,
        builder,
        expected_code,
    ):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = builder(document)

        result = _convert_document(document)
        problem_records = build_problem_records(result)
        review_items = build_review_items(result, problem_records)
        unresolved = tuple(
            item
            for item in review_items
            if item.status == "unresolved"
            and item.source_handles == (insert.dxf.handle,)
        )

        self.assertFalse(result.can_import)
        self.assertFalse(
            any(insert.dxf.handle in member.source_handles for member in result.struts)
        )
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].role, "strut")
        self.assertEqual(
            {problem.code for problem in unresolved[0].problems},
            {expected_code},
        )
        self.assertEqual(
            tuple(
                record.code
                for record in problem_records
                if record.source_handles == (insert.dxf.handle,)
            ),
            (expected_code,),
        )
        self.assertFalse(
            any(
                message.code == "AMBIGUOUS_CENTERLINE"
                and insert.dxf.handle in message.source_handles
                for message in result.messages
            )
        )

    def test_conflicting_whole_axes_create_one_unresolved_root_source(self):
        self.assert_terminal_source_problem(
            _add_ambiguous_strut_insert,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_conflicting_full_span_topology_creates_one_unresolved_root_source(self):
        self.assert_terminal_source_problem(
            _add_topology_conflict_insert,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_unreliable_whole_extent_creates_one_unresolved_root_source(self):
        self.assert_terminal_source_problem(
            _add_unreliable_extent_strut_insert,
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE",
        )


class BIMBlockReviewLifecycleIntegrationTests(unittest.TestCase):
    roles = {
        STRUT_LAYER: "strut",
        WALER_LAYER: "waler",
    }
    brace_roles = {
        BRACE_LAYER: "brace",
        STRUT_LAYER: "strut",
        WALER_LAYER: "waler",
    }

    def saved_importer(self, document):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "bim-review-source.dxf"
        document.saveas(path)
        source_bytes = path.read_bytes()
        importer = DXFImporter(path).read()
        return path, importer, source_bytes

    @staticmethod
    def review_item_for_source(result, source_handle, *, status):
        return next(
            item
            for item in build_review_items(result, build_problem_records(result))
            if item.status == status
            and item.source_handles == (source_handle,)
        )

    def test_recognized_bim_source_exclusion_restore_preserves_source_file(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_strut_insert(document)
        path, importer, source_bytes = self.saved_importer(document)
        source_hash = hashlib.sha256(source_bytes).hexdigest()

        baseline = importer.convert(layer_roles=self.roles)
        item = self.review_item_for_source(
            baseline,
            insert.dxf.handle,
            status="recognized",
        )
        exclusion = excluded_source_from_review_item(item, baseline)
        excluded = importer.convert(
            layer_roles=self.roles,
            excluded_sources=(exclusion,),
        )
        restored = importer.convert(layer_roles=self.roles)

        self.assertEqual(len(baseline.struts), 1)
        self.assertEqual(excluded.struts, ())
        self.assertEqual(excluded.source_geometry, baseline.source_geometry)
        self.assertTrue(
            any(
                candidate.status == "excluded"
                and candidate.source_handles == (insert.dxf.handle,)
                for candidate in build_review_items(
                    excluded,
                    build_problem_records(excluded),
                )
            )
        )
        self.assertEqual(restored.struts, baseline.struts)
        self.assertEqual(restored.source_geometry, baseline.source_geometry)
        self.assertEqual(path.read_bytes(), source_bytes)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)
        self.assertEqual(
            DXFImporter(path).read().source_fingerprint,
            importer.source_fingerprint,
        )

    def test_unresolved_bim_source_exclusion_restore_preserves_source_file(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_ambiguous_strut_insert(document)
        path, importer, source_bytes = self.saved_importer(document)
        source_hash = hashlib.sha256(source_bytes).hexdigest()

        baseline = importer.convert(layer_roles=self.roles)
        item = self.review_item_for_source(
            baseline,
            insert.dxf.handle,
            status="unresolved",
        )
        exclusion = excluded_source_from_review_item(item, baseline)
        excluded = importer.convert(
            layer_roles=self.roles,
            excluded_sources=(exclusion,),
        )
        restored = importer.convert(layer_roles=self.roles)

        self.assertFalse(
            any(
                message.code == "BIM_BLOCK_CONFLICTING_WHOLE_AXES"
                for message in excluded.messages
            )
        )
        self.assertEqual(excluded.source_geometry, baseline.source_geometry)
        self.assertTrue(
            any(
                candidate.status == "excluded"
                and candidate.source_handles == (insert.dxf.handle,)
                for candidate in build_review_items(
                    excluded,
                    build_problem_records(excluded),
                )
            )
        )
        restored_item = self.review_item_for_source(
            restored,
            insert.dxf.handle,
            status="unresolved",
        )
        self.assertEqual(
            {problem.code for problem in restored_item.problems},
            {"BIM_BLOCK_CONFLICTING_WHOLE_AXES"},
        )
        self.assertEqual(path.read_bytes(), source_bytes)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), source_hash)
        self.assertEqual(restored.source_fingerprint, importer.source_fingerprint)

    def test_manual_replay_targets_one_exact_root_and_reports_nonunique_or_missing(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        first_insert = _add_fragmented_strut_insert(document)
        second_insert = document.modelspace().add_blockref(
            "FRAGMENTED_STRUT",
            (0.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )
        baseline = _convert_document(document)
        first_member = next(
            member
            for member in baseline.struts
            if member.source_handles == (first_insert.dxf.handle,)
        )
        adjusted = set_cad_engineering_line(
            baseline,
            first_member.id,
            (0.0, 50.0),
            (12000.0, 50.0),
            GeometryTolerances(),
        )
        overrides = capture_manual_overrides(adjusted)
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0].source_handles, (first_insert.dxf.handle,))

        fresh = _convert_document(document)
        replayed, report = replay_manual_overrides(
            fresh,
            overrides,
            tolerances=GeometryTolerances(),
        )
        first_replayed = next(
            member
            for member in replayed.struts
            if member.source_handles == (first_insert.dxf.handle,)
        )
        second_replayed = next(
            member
            for member in replayed.struts
            if member.source_handles == (second_insert.dxf.handle,)
        )
        self.assertEqual(first_replayed.selection_source, "cad_manual")
        self.assertEqual(first_replayed.world_start, (0.0, 50.0))
        self.assertEqual(first_replayed.world_end, (12000.0, 50.0))
        self.assertEqual(second_replayed.selection_source, "auto")
        self.assertEqual(len(report.preserved), 1)
        self.assertEqual(report.needs_review, ())

        nonunique_result, nonunique_report = replay_manual_overrides(
            fresh,
            (overrides[0], overrides[0]),
            tolerances=GeometryTolerances(),
        )
        self.assertEqual(nonunique_result.struts, fresh.struts)
        self.assertEqual(nonunique_report.preserved, ())
        self.assertEqual(len(nonunique_report.needs_review), 1)

        missing = replace(
            fresh,
            struts=tuple(
                member
                for member in fresh.struts
                if member.source_handles != (first_insert.dxf.handle,)
            ),
        )
        missing_result, missing_report = replay_manual_overrides(
            missing,
            overrides,
            tolerances=GeometryTolerances(),
        )
        self.assertEqual(missing_result.struts, missing.struts)
        self.assertEqual(missing_report.preserved, ())
        self.assertEqual(len(missing_report.needs_review), 1)

    def test_changed_bim_member_geometry_invalidates_confirmation_signature(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_strut_insert(document)
        baseline = _convert_document(document)
        original_item = self.review_item_for_source(
            baseline,
            insert.dxf.handle,
            status="recognized",
        )
        confirmations = confirm_review_item(baseline, original_item)
        identity = review_confirmation_identity(original_item)
        self.assertTrue(
            review_item_is_confirmed(baseline, original_item, confirmations)
        )

        changed = set_cad_engineering_line(
            baseline,
            original_item.member_id,
            (0.0, 50.0),
            (12000.0, 50.0),
            GeometryTolerances(),
        )
        changed_item = self.review_item_for_source(
            changed,
            insert.dxf.handle,
            status="recognized",
        )
        valid = valid_review_confirmations(
            changed,
            build_review_items(changed, build_problem_records(changed)),
            confirmations,
        )

        self.assertEqual(review_confirmation_identity(changed_item), identity)
        self.assertFalse(
            review_item_is_confirmed(changed, changed_item, confirmations)
        )
        self.assertEqual(valid, {})

    def test_pause_resume_and_project_boundary_keep_bim_metadata_out_of_project(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_strut_insert(document)
        path, importer, _source_bytes = self.saved_importer(document)

        workflow = DXFReviewWorkflow(importer, path)
        workflow.recognize(self.roles)
        paused_state = workflow.serialize_review_state(
            layer_roles=self.roles,
            import_mode="replace",
        )
        resumed = DXFReviewWorkflow(
            DXFImporter(path).read(),
            path,
            initial_state=paused_state,
            resume_review=True,
        )
        resumed.recognize(self.roles)

        self.assertEqual(resumed.world_result.source_fingerprint, importer.source_fingerprint)
        self.assertEqual(len(resumed.result.struts), 1)
        member = resumed.result.struts[0]
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")

        project_rows = resumed.result.to_project_rows()
        strut_row = project_rows["struts"][0]
        for dxf_only_field in (
            "recognition_method",
            "source_handles",
            "source_layer",
            "source_entity_types",
            "block_instances",
            "source_geometry",
        ):
            self.assertNotIn(dxf_only_field, strut_row)
        project = ProjectDataModel(
            walers=project_rows["walers"],
            struts=project_rows["struts"],
            braces=project_rows["braces"],
        )
        restored_project = ProjectDataModel.from_case_data(project.to_case_data())
        self.assertEqual(restored_project.struts, project.struts)
        self.assertEqual(len(restored_project.struts), 1)

    def test_recognized_brace_exclusion_and_restore_use_exact_root_identity(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_brace_insert(document)
        path, importer, source_bytes = self.saved_importer(document)

        baseline = importer.convert(layer_roles=self.brace_roles)
        item = self.review_item_for_source(
            baseline,
            insert.dxf.handle,
            status="recognized",
        )
        exclusion = excluded_source_from_review_item(item, baseline)
        excluded = importer.convert(
            layer_roles=self.brace_roles,
            excluded_sources=(exclusion,),
        )
        restored = importer.convert(layer_roles=self.brace_roles)

        self.assertEqual(len(baseline.braces), 1)
        self.assertEqual(exclusion.role, "brace")
        self.assertEqual(exclusion.source_handles, (insert.dxf.handle,))
        self.assertEqual(excluded.braces, ())
        self.assertTrue(
            any(
                candidate.status == "excluded"
                and candidate.role == "brace"
                and candidate.source_handles == (insert.dxf.handle,)
                for candidate in build_review_items(
                    excluded,
                    build_problem_records(excluded),
                )
            )
        )
        self.assertEqual(restored.braces, baseline.braces)
        self.assertEqual(path.read_bytes(), source_bytes)

    def test_brace_manual_endpoint_replay_targets_exact_root(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_brace_insert(document)
        baseline = _convert_document(document)
        member = baseline.braces[0]
        adjusted = set_cad_engineering_line(
            baseline,
            member.id,
            (0.0, 50.0),
            (12000.0, 50.0),
            GeometryTolerances(),
        )
        overrides = capture_manual_overrides(adjusted)

        replayed, report = replay_manual_overrides(
            _convert_document(document),
            overrides,
            tolerances=GeometryTolerances(),
        )

        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0].role, "brace")
        self.assertEqual(overrides[0].source_handles, (insert.dxf.handle,))
        self.assertEqual(replayed.braces[0].selection_source, "cad_manual")
        self.assertEqual(replayed.braces[0].world_start, (0.0, 50.0))
        self.assertEqual(replayed.braces[0].world_end, (12000.0, 50.0))
        self.assertEqual(len(report.preserved), 1)
        self.assertEqual(report.needs_review, ())

    def test_changed_brace_geometry_invalidates_confirmation_signature(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        insert = _add_fragmented_brace_insert(document)
        baseline = _convert_document(document)
        original_item = self.review_item_for_source(
            baseline,
            insert.dxf.handle,
            status="recognized",
        )
        confirmations = confirm_review_item(baseline, original_item)
        identity = review_confirmation_identity(original_item)

        changed = set_cad_engineering_line(
            baseline,
            original_item.member_id,
            (0.0, 50.0),
            (12000.0, 50.0),
            GeometryTolerances(),
        )
        changed_item = self.review_item_for_source(
            changed,
            insert.dxf.handle,
            status="recognized",
        )

        self.assertEqual(identity, f"brace:{insert.dxf.handle}")
        self.assertFalse(
            review_item_is_confirmed(changed, changed_item, confirmations)
        )
        self.assertEqual(
            valid_review_confirmations(
                changed,
                build_review_items(changed, build_problem_records(changed)),
                confirmations,
            ),
            {},
        )

    def test_ambiguous_brace_blocks_completion_until_source_is_resolved(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        _add_single_line_insert(
            document,
            block_name="REQUIRED_STRUT_FOR_BRACE_REVIEW",
            root_layer=STRUT_LAYER,
        )
        insert = _add_ambiguous_brace_insert(document)
        path, importer, _source_bytes = self.saved_importer(document)
        workflow = DXFReviewWorkflow(importer, path)

        workflow.recognize(self.brace_roles)

        item = self.review_item_for_source(
            workflow.result,
            insert.dxf.handle,
            status="unresolved",
        )
        status = workflow.completion_status()
        self.assertEqual(item.role, "brace")
        self.assertFalse(status.can_import)
        self.assertGreater(status.blocking_error_count, 0)

    def test_brace_pause_resume_and_project_boundary_use_existing_row_schema(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        _add_single_line_insert(
            document,
            block_name="REQUIRED_STRUT_FOR_BRACE_PROJECT",
            root_layer=STRUT_LAYER,
        )
        insert = _add_fragmented_brace_insert(document)
        path, importer, _source_bytes = self.saved_importer(document)
        workflow = DXFReviewWorkflow(importer, path)
        workflow.recognize(self.brace_roles)
        paused_state = workflow.serialize_review_state(
            layer_roles=self.brace_roles,
            import_mode="replace",
        )

        resumed = DXFReviewWorkflow(
            DXFImporter(path).read(),
            path,
            initial_state=paused_state,
            resume_review=True,
        )
        resumed.recognize(self.brace_roles)

        self.assertEqual(len(resumed.result.braces), 1)
        member = resumed.result.braces[0]
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        brace_row = resumed.result.to_project_rows()["braces"][0]
        self.assertEqual(
            set(brace_row),
            {
                "BraceID",
                "FromWaler",
                "ToWaler",
                "StartX",
                "StartY",
                "EndX",
                "EndY",
            },
        )
        project_rows = resumed.result.to_project_rows()
        project = ProjectDataModel(
            walers=project_rows["walers"],
            struts=project_rows["struts"],
            braces=project_rows["braces"],
        )
        restored_project = ProjectDataModel.from_case_data(project.to_case_data())
        self.assertEqual(restored_project.braces, project.braces)
        self.assertEqual(len(restored_project.braces), 1)


class BIMBlockCandidateDeduplicationTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def candidate(root_handle, recognition_method):
        return _Candidate(
            (0.0, 0.0),
            (12000.0, 0.0),
            recognition_method,
            True,
            400.0,
            0.9,
            STRUT_LAYER,
            {root_handle},
            {"INSERT", "LWPOLYLINE"},
            [],
            {f"strut:{root_handle}"},
            [],
        )

    def test_collinear_bim_candidates_from_different_roots_remain_separate(self):
        first = self.candidate("ROOT-A", "bim_block_whole_axis")
        second = self.candidate("ROOT-B", "bim_block_whole_axis")

        kept, messages = _deduplicate_candidates(
            (first, second),
            "strut",
            self.tolerances,
        )

        self.assertEqual(len(kept), 2)
        self.assertEqual(
            {tuple(candidate.handles) for candidate in kept},
            {("ROOT-A",), ("ROOT-B",)},
        )
        self.assertEqual(messages, [])

    def test_identical_root_inserts_remain_two_provenance_distinct_members(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        first = _add_fragmented_strut_insert(document)
        second = document.modelspace().add_blockref(
            "FRAGMENTED_STRUT",
            (0.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )

        result = _convert_document(document)

        self.assertEqual(len(result.struts), 2)
        self.assertEqual(
            {member.source_handles for member in result.struts},
            {(first.dxf.handle,), (second.dxf.handle,)},
        )
        self.assertTrue(
            all(
                member.recognition_method == "bim_block_whole_axis"
                for member in result.struts
            )
        )
        self.assertFalse(
            any(message.code == "DUPLICATED_COMPONENT" for message in result.messages)
        )

    def test_general_candidate_deduplication_keeps_existing_behavior(self):
        centerline = self.candidate("LINE-A", "existing_centerline")
        outline = self.candidate("OUTLINE-B", "closed_outline_axis")

        kept, messages = _deduplicate_candidates(
            (centerline, outline),
            "strut",
            self.tolerances,
        )

        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].handles, {"LINE-A", "OUTLINE-B"})
        self.assertEqual([message.code for message in messages], ["DUPLICATED_COMPONENT"])


class BIMBlockOrdinaryCompoundFallbackTests(unittest.TestCase):
    def test_unrelated_ordinary_compound_block_preserves_general_fallback(self):
        document = _new_document()
        insert = _add_ordinary_compound_insert(document)
        groups, _source_geometry = _extract_strut_groups(document)
        group = groups[0]

        outcome = recognize_component_like_strut(
            _recognition_source_from_group(group),
            GeometryTolerances(),
        )
        candidate, messages = _candidate_from_group(
            group,
            "strut",
            GeometryTolerances(),
        )

        self.assertEqual(group.root_handle, insert.dxf.handle)
        self.assertEqual(len(group.primitives), 3)
        self.assertTrue(all(not item.closed for item in group.primitives))
        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)
        self.assertIsNone(candidate)
        self.assertEqual(messages, [])


class BIMStrutOutlineTopologyCharacterizationTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def closed_envelope(width):
        half_width = width / 2.0
        return BlockMemberPrimitive(
            (
                (0.0, -half_width),
                (12000.0, -half_width),
                (12000.0, half_width),
                (0.0, half_width),
            ),
            True,
            "LWPOLYLINE",
        )

    @staticmethod
    def connected_line_envelope(width):
        half_width = width / 2.0
        points = (
            (0.0, -half_width),
            (12000.0, -half_width),
            (12000.0, half_width),
            (0.0, half_width),
        )
        return tuple(
            BlockMemberPrimitive(
                (points[index], points[(index + 1) % len(points)]),
                False,
                "LINE",
            )
            for index in range(len(points))
        )

    def test_y05_s10_fixture_captures_the_current_cross_pair_fallback(self):
        source = _y05_s10_recognition_source()
        fragments = _extract_fragment_axes(source.primitives, self.tolerances)
        outline = tuple(
            fragment
            for fragment in fragments
            if fragment.kind is FragmentEvidenceKind.OUTLINE
        )
        weak = tuple(
            fragment
            for fragment in fragments
            if fragment.kind is FragmentEvidenceKind.WEAK_LINE
        )
        candidate, messages = _candidate_from_group(
            _group_from_recognition_source(source),
            "strut",
            self.tolerances,
        )

        self.assertEqual(len(source.primitives), 8)
        self.assertEqual(len(outline), 1)
        self.assertAlmostEqual(outline[0].width, 350.0)
        self.assertEqual(len(weak), 1)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.recognition_method, "parallel_edges_midline")
        self.assertAlmostEqual(candidate.start[0], -15414.0)
        self.assertAlmostEqual(candidate.end[0], -15414.0)
        self.assertAlmostEqual(candidate.source_width, 181.0)
        self.assertEqual(
            {message.code for message in messages},
            {"AMBIGUOUS_CENTERLINE"},
        )

    def test_closed_and_connected_envelopes_share_axis_but_keep_provenance_shape(self):
        closed_fragments = _extract_fragment_axes(
            (self.closed_envelope(400.0),),
            self.tolerances,
        )
        connected_fragments = _extract_fragment_axes(
            self.connected_line_envelope(400.0),
            self.tolerances,
        )

        self.assertEqual(len(closed_fragments), 1)
        self.assertEqual(len(connected_fragments), 1)
        self.assertIs(closed_fragments[0].kind, FragmentEvidenceKind.OUTLINE)
        self.assertIs(connected_fragments[0].kind, FragmentEvidenceKind.OUTLINE)
        self.assertEqual(closed_fragments[0].axis, connected_fragments[0].axis)
        self.assertEqual(len(closed_fragments[0].source_segment_ids), 4)
        self.assertEqual(len(connected_fragments[0].source_segment_ids), 4)

    def test_open_parallel_rails_are_only_local_fragment_evidence_without_end_caps(self):
        open_rails = (
            BlockMemberPrimitive(
                ((0.0, -200.0), (12000.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((0.0, 200.0), (12000.0, 200.0)),
                False,
                "LINE",
            ),
        )
        closed_by_end_caps = open_rails + (
            BlockMemberPrimitive(
                ((0.0, -200.0), (0.0, 200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((12000.0, -200.0), (12000.0, 200.0)),
                False,
                "LINE",
            ),
        )

        open_fragments = _extract_fragment_axes(open_rails, self.tolerances)
        connected_fragments = _extract_fragment_axes(
            closed_by_end_caps,
            self.tolerances,
        )

        self.assertEqual(len(open_fragments), 1)
        self.assertIs(open_fragments[0].kind, FragmentEvidenceKind.RAIL_PAIR)
        self.assertEqual(len(connected_fragments), 1)
        self.assertIs(connected_fragments[0].kind, FragmentEvidenceKind.OUTLINE)

    def test_variable_width_and_ambiguous_envelope_fixtures_are_distinct(self):
        for width in (350.0, 400.0, 500.0):
            with self.subTest(width=width):
                fragments = _extract_fragment_axes(
                    (self.closed_envelope(width),),
                    self.tolerances,
                )
                self.assertEqual(len(fragments), 1)
                self.assertAlmostEqual(fragments[0].width, width)

        nested = _extract_fragment_axes(
            (
                self.closed_envelope(400.0),
                self.closed_envelope(500.0),
            ),
            self.tolerances,
        )
        self.assertEqual(
            sorted(fragment.width for fragment in nested),
            [400.0, 500.0],
        )


class BIMStrutOutlineTopologyGuardTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives, *, root_handle="TOPOLOGY-ROOT"):
        return BlockMemberRecognitionInput(
            root_handle=root_handle,
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def envelope(width, *, center_y=0.0, closed=True):
        half_width = width / 2.0
        points = (
            (0.0, center_y - half_width),
            (12000.0, center_y - half_width),
            (12000.0, center_y + half_width),
            (0.0, center_y + half_width),
        )
        if closed:
            return (
                BlockMemberPrimitive(points, True, "LWPOLYLINE"),
            )
        return tuple(
            BlockMemberPrimitive(
                (points[index], points[(index + 1) % len(points)]),
                False,
                "LINE",
            )
            for index in range(len(points))
        )

    def test_topology_members_require_closed_cycle_or_connected_end_caps(self):
        closed = _extract_topology_members(
            self.envelope(400.0),
            self.tolerances,
        )
        connected = _extract_topology_members(
            self.envelope(400.0, closed=False),
            self.tolerances,
        )
        open_rails = (
            BlockMemberPrimitive(
                ((0.0, -200.0), (12000.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((0.0, 200.0), (12000.0, 200.0)),
                False,
                "LINE",
            ),
        )

        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].kind, "closed_outline")
        self.assertEqual(len(connected), 1)
        self.assertEqual(connected[0].kind, "connected_contour")
        self.assertEqual(
            _extract_topology_members(open_rails, self.tolerances),
            (),
        )

    def test_dangling_branch_preserves_independent_boundary_but_duplicate_does_not(self):
        connected = self.envelope(400.0, closed=False)
        branch = BlockMemberPrimitive(
            ((0.0, -200.0), (-200.0, -200.0)),
            False,
            "LINE",
        )

        members = _extract_topology_members(
            connected + (branch,),
            self.tolerances,
        )

        self.assertEqual(len(members), 1)
        self.assertEqual(members[0].axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(members[0].width, 400.0)
        self.assertEqual(
            _extract_topology_members(
                connected + (connected[0],),
                self.tolerances,
            ),
            (),
        )

    def test_outer_boundary_excludes_dangling_branch_from_component_width(self):
        valid_inner = self.envelope(400.0)
        independent_outer = self.envelope(500.0, closed=False)
        branch = BlockMemberPrimitive(
            ((0.0, -250.0), (-300.0, -250.0)),
            False,
            "LINE",
        )

        outcome = recognize_component_like_strut(
            self.source(valid_inner + independent_outer + (branch,)),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 500.0)

    def test_epsilon_offset_corner_uses_one_canonical_topology_node(self):
        epsilon = 1e-10
        primitives = (
            BlockMemberPrimitive(
                ((0.0, -200.0), (12000.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((12000.0 + epsilon, -200.0), (12000.0, 200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((12000.0, 200.0), (0.0, 200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((0.0, 200.0), (0.0, -200.0)),
                False,
                "LINE",
            ),
        )
        raw_points = {
            point
            for primitive in primitives
            for point in primitive.points
        }

        members = _extract_topology_members(primitives, self.tolerances)
        reversed_members = _extract_topology_members(
            tuple(
                replace(primitive, points=tuple(reversed(primitive.points)))
                for primitive in reversed(primitives)
            ),
            self.tolerances,
        )

        self.assertEqual(len(raw_points), 5)
        self.assertEqual(len(members), 1)
        self.assertEqual(len(members[0].points), 4)
        self.assertAlmostEqual(members[0].axis[0][1], 0.0, places=6)
        self.assertAlmostEqual(members[0].axis[1][1], 0.0, places=6)
        self.assertAlmostEqual(members[0].width, 400.0, places=6)
        self.assertEqual(len(reversed_members), 1)
        self.assertAlmostEqual(reversed_members[0].axis[0][1], 0.0, places=6)
        self.assertAlmostEqual(reversed_members[0].width, 400.0, places=6)

    def test_y05_s10_uses_outer_contour_axis_and_width(self):
        outcome = recognize_component_like_strut(
            _y05_s10_recognition_source(),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.whole_axis[0][0], -15498.5)
        self.assertAlmostEqual(outcome.whole_axis[0][1], -23550.05)
        self.assertAlmostEqual(outcome.whole_axis[1][0], -15498.5)
        self.assertAlmostEqual(outcome.whole_axis[1][1], 8450.0)
        self.assertAlmostEqual(outcome.representative_width, 350.0)
        self.assertEqual(outcome.accepted_fragment_count, 1)

    def test_nested_equivalent_envelopes_use_the_unique_outer_width(self):
        primitives = self.envelope(400.0) + self.envelope(500.0)

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 500.0)

    def test_unique_axis_without_unique_envelope_keeps_unknown_width(self):
        primitives = self.envelope(500.0, center_y=-25.0) + self.envelope(
            480.0,
            center_y=25.0,
        )

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.representative_width, 0.0)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))

        reordered = recognize_component_like_strut(
            self.source(tuple(reversed(primitives))),
            self.tolerances,
        )
        self.assertEqual(reordered.status, outcome.status)
        self.assertEqual(reordered.whole_axis, outcome.whole_axis)
        self.assertEqual(reordered.representative_width, 0.0)

    def test_two_non_equivalent_full_span_topologies_are_ambiguous(self):
        first = self.envelope(400.0, center_y=-350.0)
        second = self.envelope(400.0, center_y=350.0)

        outcome = recognize_component_like_strut(
            self.source(first + second),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_equivalence_tolerance_does_not_merge_a_transitive_axis_chain(self):
        primitives = tuple(
            primitive
            for center_y in (0.0, 50.0, 100.0)
            for primitive in self.envelope(200.0, center_y=center_y)
        )

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_single_legacy_envelope_still_uses_general_recognition(self):
        primitives = self.envelope(400.0)

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )
        candidate, messages = _candidate_from_group(
            _group_from_recognition_source(self.source(primitives)),
            "strut",
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.recognition_method, "closed_outline_axis")
        self.assertAlmostEqual(candidate.source_width, 400.0)
        self.assertEqual(messages, [])

    def test_variable_single_envelopes_keep_their_actual_width(self):
        for width in (350.0, 400.0, 500.0):
            with self.subTest(width=width):
                source = self.source(self.envelope(width))
                route = _route_component_like_strut_block(
                    _group_from_recognition_source(source),
                    self.tolerances,
                )
                candidate, messages = _candidate_from_group(
                    _group_from_recognition_source(source),
                    "strut",
                    self.tolerances,
                )

                self.assertFalse(route.handled)
                self.assertIsNotNone(candidate)
                self.assertAlmostEqual(candidate.source_width, width)
                self.assertEqual(messages, [])

    def test_d17_topology_outcome_is_independent_of_child_order_and_line_direction(self):
        source = _y05_s10_recognition_source()
        expected = recognize_component_like_strut(source, self.tolerances)
        reversed_lines = tuple(
            BlockMemberPrimitive(
                tuple(reversed(primitive.points)),
                primitive.closed,
                primitive.entity_type,
                primitive.source_handle,
                primitive.source_width,
            )
            for primitive in reversed(source.primitives)
        )
        actual = recognize_component_like_strut(
            self.source(reversed_lines, root_handle="D17"),
            self.tolerances,
        )

        self.assertEqual(actual.status, expected.status)
        self.assertEqual(actual.whole_axis, expected.whole_axis)
        self.assertAlmostEqual(
            actual.representative_width,
            expected.representative_width,
        )

    def test_closed_traversal_and_equivalent_duplicate_preserve_final_outcome(self):
        inner = self.envelope(400.0)[0]
        outer = self.envelope(500.0)[0]
        expected = recognize_component_like_strut(
            self.source((inner, outer)),
            self.tolerances,
        )

        def reindex(primitive, offset):
            points = list(primitive.points)
            points = points[offset:] + points[:offset]
            return BlockMemberPrimitive(
                tuple(reversed(points)),
                primitive.closed,
                primitive.entity_type,
            )

        actual = recognize_component_like_strut(
            self.source(
                (
                    reindex(outer, 1),
                    reindex(inner, 2),
                    reindex(inner, 3),
                )
            ),
            self.tolerances,
        )

        self.assertEqual(actual.status, expected.status)
        self.assertEqual(actual.whole_axis, expected.whole_axis)
        self.assertAlmostEqual(
            actual.representative_width,
            expected.representative_width,
        )

    def test_nested_envelope_center_and_width_survive_rotation_and_translation(self):
        angle = math.radians(31.0)
        cosine, sine = math.cos(angle), math.sin(angle)

        def transform(point):
            return (
                point[0] * cosine - point[1] * sine + 1234.0,
                point[0] * sine + point[1] * cosine - 5678.0,
            )

        primitives = self.envelope(400.0) + self.envelope(500.0)
        transformed = tuple(
            replace(
                primitive,
                points=tuple(transform(point) for point in primitive.points),
            )
            for primitive in primitives
        )

        outcome = recognize_component_like_strut(
            self.source(transformed),
            self.tolerances,
        )
        expected_axis = tuple(sorted((transform((0.0, 0.0)), transform((12000.0, 0.0)))))

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.whole_axis[0][0], expected_axis[0][0], places=6)
        self.assertAlmostEqual(outcome.whole_axis[0][1], expected_axis[0][1], places=6)
        self.assertAlmostEqual(outcome.whole_axis[1][0], expected_axis[1][0], places=6)
        self.assertAlmostEqual(outcome.whole_axis[1][1], expected_axis[1][1], places=6)
        self.assertAlmostEqual(outcome.representative_width, 500.0, places=6)


class BlockMemberRecognitionContractTests(unittest.TestCase):
    def test_input_requires_explicit_root_source_identity(self):
        primitive = BlockMemberPrimitive(
            points=((0.0, 0.0), (1000.0, 0.0)),
            closed=False,
            entity_type="LINE",
        )

        with self.assertRaises(ValueError):
            BlockMemberRecognitionInput("", "INSERT", "strut", (primitive,))

    def test_recognized_outcome_normalizes_axis_and_requires_geometry(self):
        outcome = BlockMemberRecognitionOutcome.recognized(
            ((1000.0, 0.0), (0.0, 0.0)),
            representative_width=400.0,
            confidence=1.0,
            accepted_fragment_count=2,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (1000.0, 0.0)))
        unknown_width = BlockMemberRecognitionOutcome.recognized(
            ((0.0, 0.0), (1000.0, 0.0)),
            representative_width=0.0,
            confidence=1.0,
            accepted_fragment_count=1,
        )
        self.assertEqual(unknown_width.representative_width, 0.0)
        with self.assertRaises(ValueError):
            BlockMemberRecognitionOutcome.recognized(
                ((0.0, 0.0), (0.0, 0.0)),
                representative_width=400.0,
                confidence=1.0,
                accepted_fragment_count=1,
            )

    def test_terminal_outcomes_require_diagnostics_and_never_expose_axis(self):
        failed = BlockMemberRecognitionOutcome.failed("WHOLE_EXTENT_UNRELIABLE")
        ambiguous = BlockMemberRecognitionOutcome.ambiguous("CONFLICTING_AXES")

        self.assertIs(failed.status, BlockMemberRecognitionStatus.FAILED)
        self.assertIs(ambiguous.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertIsNone(failed.whole_axis)
        self.assertIsNone(ambiguous.whole_axis)
        with self.assertRaises(ValueError):
            BlockMemberRecognitionOutcome(BlockMemberRecognitionStatus.FAILED)

    def test_not_applicable_has_no_blocking_diagnostic(self):
        outcome = BlockMemberRecognitionOutcome.not_applicable()

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)
        self.assertEqual(outcome.diagnostic_code, "")

    def test_pure_service_module_has_no_review_or_presentation_dependency(self):
        module_path = PROJECT_ROOT / "dxf_import" / "block_member_recognition.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }

        self.assertFalse(
            {
                "dialog",
                "controllers",
                "preview",
                "review_workflow",
                "candidate_points",
                "importer",
                "dxf_import.dialog",
                "dxf_import.candidate_points",
                "dxf_import.importer",
                "dxf_import.review_workflow",
            }.intersection(imported_modules)
        )


class BlockMemberFragmentExtractionTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    def assert_axis_almost_equal(self, actual, expected, *, places=6):
        for actual_point, expected_point in zip(actual, expected):
            self.assertAlmostEqual(actual_point[0], expected_point[0], places=places)
            self.assertAlmostEqual(actual_point[1], expected_point[1], places=places)

    @staticmethod
    def rectangle_polyline():
        return BlockMemberPrimitive(
            points=(
                (0.0, -200.0),
                (2000.0, -200.0),
                (2000.0, 200.0),
                (0.0, 200.0),
            ),
            closed=True,
            entity_type="LWPOLYLINE",
        )

    @staticmethod
    def rectangle_lines():
        points = (
            (0.0, -200.0),
            (2000.0, -200.0),
            (2000.0, 200.0),
            (0.0, 200.0),
        )
        return tuple(
            BlockMemberPrimitive(
                points=(points[index], points[(index + 1) % len(points)]),
                closed=False,
                entity_type="LINE",
            )
            for index in range(len(points))
        )

    def test_line_and_polyline_rectangles_produce_equivalent_fragment_axes(self):
        polyline_fragments = _extract_fragment_axes(
            (self.rectangle_polyline(),),
            self.tolerances,
        )
        line_fragments = _extract_fragment_axes(
            self.rectangle_lines(),
            self.tolerances,
        )

        self.assertEqual(len(polyline_fragments), 1)
        self.assertEqual(len(line_fragments), 1)
        self.assertIs(polyline_fragments[0].kind, FragmentEvidenceKind.OUTLINE)
        self.assertIs(line_fragments[0].kind, FragmentEvidenceKind.OUTLINE)
        self.assert_axis_almost_equal(
            polyline_fragments[0].axis,
            line_fragments[0].axis,
        )
        self.assertAlmostEqual(polyline_fragments[0].width, 400.0)
        self.assertAlmostEqual(line_fragments[0].width, 400.0)

    def test_legal_local_rail_pair_produces_one_strong_fragment(self):
        rails = (
            BlockMemberPrimitive(
                ((0.0, -200.0), (2000.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((0.0, 200.0), (2000.0, 200.0)),
                False,
                "LINE",
            ),
        )

        fragments = _extract_fragment_axes(rails, self.tolerances)

        self.assertEqual(len(fragments), 1)
        self.assertIs(fragments[0].kind, FragmentEvidenceKind.RAIL_PAIR)
        self.assertTrue(fragments[0].is_strong)
        self.assert_axis_almost_equal(
            fragments[0].axis,
            ((0.0, 0.0), (2000.0, 0.0)),
        )

    def test_unpaired_single_line_is_only_weak_evidence(self):
        line = BlockMemberPrimitive(
            ((0.0, 0.0), (2000.0, 0.0)),
            False,
            "LINE",
        )

        fragments = _extract_fragment_axes((line,), self.tolerances)

        self.assertEqual(len(fragments), 1)
        self.assertIs(fragments[0].kind, FragmentEvidenceKind.WEAK_LINE)
        self.assertFalse(fragments[0].is_strong)


class BlockMemberOrientationClusteringTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def rectangle(
        start: float,
        end: float,
        *,
        center_y: float = 0.0,
        reverse: bool = False,
    ) -> BlockMemberPrimitive:
        points = (
            (start, center_y - 200.0),
            (end, center_y - 200.0),
            (end, center_y + 200.0),
            (start, center_y + 200.0),
        )
        return BlockMemberPrimitive(
            tuple(reversed(points)) if reverse else points,
            True,
            "LWPOLYLINE",
        )

    @staticmethod
    def transverse_details() -> tuple[BlockMemberPrimitive, ...]:
        return tuple(
            BlockMemberPrimitive(
                ((station, -40.0), (station, 40.0)),
                False,
                "LINE",
            )
            for station in range(500, 11501, 500)
        )

    def test_reversal_reordering_and_short_details_preserve_dominant_axis(self):
        ordered = (
            self.rectangle(0.0, 2200.0),
            self.rectangle(3100.0, 5200.0, reverse=True),
            self.rectangle(6800.0, 8900.0),
            self.rectangle(10100.0, 12000.0, reverse=True),
        )
        permuted = tuple(reversed(ordered)) + self.transverse_details()

        first_clusters = _build_orientation_clusters(
            _extract_fragment_axes(ordered, self.tolerances),
            self.tolerances,
        )
        second_clusters = _build_orientation_clusters(
            _extract_fragment_axes(permuted, self.tolerances),
            self.tolerances,
        )

        self.assertEqual(len(first_clusters), 1)
        self.assertEqual(len(second_clusters), 1)
        self.assertAlmostEqual(first_clusters[0].direction[0], 1.0)
        self.assertAlmostEqual(first_clusters[0].direction[1], 0.0)
        self.assertEqual(first_clusters[0].direction, second_clusters[0].direction)
        self.assertAlmostEqual(
            first_clusters[0].longitudinal_support,
            second_clusters[0].longitudinal_support,
        )

    def test_named_dominance_default_is_characterized_at_equal_conflict_boundary(self):
        horizontal = (
            self.rectangle(-4200.0, -100.0),
            self.rectangle(100.0, 4200.0),
        )
        vertical = tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in horizontal
        )

        clusters = _build_orientation_clusters(
            _extract_fragment_axes(horizontal + vertical, self.tolerances),
            self.tolerances,
        )
        total_support = sum(cluster.longitudinal_support for cluster in clusters)
        equal_conflict_ratio = clusters[0].longitudinal_support / total_support

        self.assertEqual(len(clusters), 2)
        self.assertAlmostEqual(equal_conflict_ratio, 0.5)
        self.assertEqual(
            self.tolerances.bim_minimum_longitudinal_evidence_ratio,
            equal_conflict_ratio,
        )


class BlockMemberComponentClassificationTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives):
        return BlockMemberRecognitionInput(
            root_handle="BIM-ROOT",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def rectangles_along_x(*, center_y=0.0):
        return tuple(
            BlockMemberOrientationClusteringTests.rectangle(
                start,
                end,
                center_y=center_y,
            )
            for start, end in (
                (0.0, 2200.0),
                (3100.0, 5200.0),
                (6800.0, 8900.0),
                (10100.0, 12000.0),
            )
        )

    @staticmethod
    def rotate_to_y(primitives):
        return tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in primitives
        )

    def test_unrelated_weak_geometry_is_not_applicable(self):
        primitives = (
            BlockMemberPrimitive(((0.0, 0.0), (2000.0, 300.0)), False, "LINE"),
            BlockMemberPrimitive(((500.0, -500.0), (700.0, 1800.0)), False, "LINE"),
            BlockMemberPrimitive(((2500.0, 900.0), (3100.0, 1200.0)), False, "LINE"),
        )

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)

    def test_one_coherent_fragment_cluster_is_recognized(self):
        outcome = recognize_component_like_strut(
            self.source(self.rectangles_along_x()),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 400.0)
        self.assertEqual(outcome.accepted_fragment_count, 4)

    def test_equal_conflicting_whole_component_clusters_are_ambiguous(self):
        horizontal = self.rectangles_along_x()
        vertical = self.rotate_to_y(horizontal)

        outcome = recognize_component_like_strut(
            self.source(horizontal + vertical),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )


class BraceBlockMemberPolicyTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives, *, root_handle="BRACE-FIXTURE"):
        return BlockMemberRecognitionInput(
            root_handle=root_handle,
            root_entity_type="INSERT",
            role="brace",
            primitives=tuple(primitives),
        )

    @staticmethod
    def rectangle(start, end, *, width=300.0, center_y=0.0):
        half_width = width / 2.0
        return BlockMemberPrimitive(
            (
                (start, center_y - half_width),
                (end, center_y - half_width),
                (end, center_y + half_width),
                (start, center_y + half_width),
            ),
            True,
            "LWPOLYLINE",
        )

    @classmethod
    def fragmented_member(cls):
        return tuple(
            cls.rectangle(start, end)
            for start, end in (
                (0.0, 2200.0),
                (3100.0, 5200.0),
                (6800.0, 8900.0),
                (10100.0, 12000.0),
            )
        )

    @staticmethod
    def rotate_to_y(primitives):
        return tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in primitives
        )

    @staticmethod
    def outcome_signature(outcome):
        return (
            outcome.status,
            outcome.whole_axis,
            round(outcome.representative_width, 6),
            outcome.diagnostic_code,
        )

    @staticmethod
    def reverse_primitive(primitive):
        return BlockMemberPrimitive(
            tuple(reversed(primitive.points)),
            primitive.closed,
            primitive.entity_type,
            primitive.source_handle,
            primitive.source_width,
        )

    @staticmethod
    def rotate_closed_path(primitive):
        points = primitive.points
        return BlockMemberPrimitive(
            points[1:] + points[:1],
            primitive.closed,
            primitive.entity_type,
            primitive.source_handle,
            primitive.source_width,
        )

    @staticmethod
    def connected_band_rails():
        return tuple(
            BlockMemberPrimitive(
                ((start, y_coordinate), (end, y_coordinate)),
                False,
                "LINE",
            )
            for y_coordinate in (-150.0, -5.0, 5.0, 150.0)
            for start, end in (
                (0.0, 2200.0),
                (3100.0, 5200.0),
                (6800.0, 8900.0),
                (10100.0, 12000.0),
            )
        )

    def test_fragmented_brace_with_interior_gaps_has_one_whole_axis(self):
        detail = self.rectangle(5800.0, 6000.0, width=100.0)

        outcome = recognize_component_like_member(
            self.source((*self.fragmented_member(), detail), root_handle="BRACE-GAPS"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))

    def test_connected_transverse_rail_bands_form_one_brace_axis(self):
        rails = self.connected_band_rails()

        outcome = recognize_component_like_member(
            self.source(rails, root_handle="BRACE-CONNECTED-BANDS"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 300.0)

    def test_child_order_and_candidate_enumeration_are_deterministic(self):
        primitives = self.connected_band_rails()
        expected = recognize_component_like_member(
            self.source(primitives, root_handle="BRACE-ORDER-BASE"),
            self.tolerances,
        )

        for index, reordered in enumerate(
            (
                tuple(reversed(primitives)),
                primitives[::2] + primitives[1::2],
                primitives[1::2] + primitives[::2],
            )
        ):
            with self.subTest(index=index):
                actual = recognize_component_like_member(
                    self.source(reordered, root_handle=f"BRACE-ORDER-{index}"),
                    self.tolerances,
                )
                self.assertEqual(
                    self.outcome_signature(actual),
                    self.outcome_signature(expected),
                )

    def test_line_direction_is_deterministic(self):
        primitives = self.connected_band_rails()
        expected = recognize_component_like_member(
            self.source(primitives, root_handle="BRACE-LINE-DIRECTION-BASE"),
            self.tolerances,
        )
        reversed_lines = tuple(
            self.reverse_primitive(primitive) for primitive in primitives
        )

        actual = recognize_component_like_member(
            self.source(
                tuple(reversed(reversed_lines)),
                root_handle="BRACE-LINE-DIRECTION-REVERSED",
            ),
            self.tolerances,
        )

        self.assertEqual(
            self.outcome_signature(actual),
            self.outcome_signature(expected),
        )

    def test_closed_path_traversal_is_deterministic(self):
        primitives = self.fragmented_member()
        expected = recognize_component_like_member(
            self.source(primitives, root_handle="BRACE-PATH-BASE"),
            self.tolerances,
        )
        variants = (
            tuple(self.reverse_primitive(item) for item in primitives),
            tuple(self.rotate_closed_path(item) for item in primitives),
            tuple(
                self.reverse_primitive(self.rotate_closed_path(item))
                for item in reversed(primitives)
            ),
        )

        for index, variant in enumerate(variants):
            with self.subTest(index=index):
                actual = recognize_component_like_member(
                    self.source(variant, root_handle=f"BRACE-PATH-{index}"),
                    self.tolerances,
                )
                self.assertEqual(
                    self.outcome_signature(actual),
                    self.outcome_signature(expected),
                )

    def test_two_disconnected_complete_rail_bands_are_ambiguous(self):
        rails = tuple(
            BlockMemberPrimitive(
                ((0.0, y_coordinate), (12000.0, y_coordinate)),
                False,
                "LINE",
            )
            for y_coordinate in (-500.0, -300.0, 300.0, 500.0)
        )

        outcome = recognize_component_like_member(
            self.source(rails, root_handle="BRACE-CONFLICT"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_perpendicular_complete_members_are_ambiguous(self):
        horizontal = self.fragmented_member()
        vertical = self.rotate_to_y(horizontal)

        outcome = recognize_component_like_member(
            self.source(horizontal + vertical, root_handle="BRACE-TWO-AXES"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)

    def test_unrelated_geometry_is_not_applicable(self):
        primitives = (
            BlockMemberPrimitive(((0.0, 0.0), (1800.0, 250.0)), False, "LINE"),
            BlockMemberPrimitive(((500.0, -600.0), (750.0, 1600.0)), False, "LINE"),
            BlockMemberPrimitive(((2300.0, 850.0), (3050.0, 1200.0)), False, "LINE"),
        )

        outcome = recognize_component_like_member(
            self.source(primitives, root_handle="BRACE-ORDINARY"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)

    def test_open_parallel_edges_without_topology_keep_general_fallback(self):
        rails = (
            BlockMemberPrimitive(((0.0, -200.0), (12000.0, -200.0)), False, "LINE"),
            BlockMemberPrimitive(((0.0, 200.0), (12000.0, 200.0)), False, "LINE"),
        )

        outcome = recognize_component_like_member(
            self.source(rails, root_handle="BRACE-OPEN-PAIR"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)

    def test_different_root_sources_are_evaluated_independently(self):
        first_root = (
            self.rectangle(0.0, 2200.0),
            self.rectangle(3100.0, 5200.0),
        )
        second_root = (
            self.rectangle(6800.0, 8900.0),
            self.rectangle(10100.0, 12000.0),
        )

        first = recognize_component_like_member(
            self.source(first_root, root_handle="BRACE-ROOT-A"),
            self.tolerances,
        )
        second = recognize_component_like_member(
            self.source(second_root, root_handle="BRACE-ROOT-B"),
            self.tolerances,
        )

        self.assertIs(first.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertIs(second.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(first.whole_axis, ((0.0, 0.0), (5200.0, 0.0)))
        self.assertEqual(second.whole_axis, ((6800.0, 0.0), (12000.0, 0.0)))

    def test_fixed_synthetic_root_handles_cover_ambiguity_and_fallback(self):
        ambiguous = recognize_component_like_member(
            self.source(
                self.fragmented_member()
                + self.rotate_to_y(self.fragmented_member()),
                root_handle="BRACE-TWO-AXES",
            ),
            self.tolerances,
        )
        fallback = recognize_component_like_member(
            self.source(
                (
                    BlockMemberPrimitive(
                        ((0.0, -200.0), (12000.0, -200.0)),
                        False,
                        "LINE",
                    ),
                    BlockMemberPrimitive(
                        ((0.0, 200.0), (12000.0, 200.0)),
                        False,
                        "LINE",
                    ),
                ),
                root_handle="BRACE-OPEN-PAIR",
            ),
            self.tolerances,
        )

        self.assertIs(ambiguous.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertIs(fallback.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)

    def test_local_pair_without_supported_terminal_extent_fails(self):
        primitives = (
            BlockMemberPrimitive(((4500.0, -200.0), (7500.0, -200.0)), False, "LINE"),
            BlockMemberPrimitive(((4500.0, 200.0), (7500.0, 200.0)), False, "LINE"),
            BlockMemberPrimitive(((0.0, -40.0), (0.0, 40.0)), False, "LINE"),
            BlockMemberPrimitive(((12000.0, -40.0), (12000.0, 40.0)), False, "LINE"),
        )

        outcome = recognize_component_like_member(
            self.source(primitives, root_handle="BRACE-UNRELIABLE-EXTENT"),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.FAILED)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE",
        )


class OrdinaryBraceAssetRegressionTests(unittest.TestCase):
    @unittest.skipUnless(Y1A_DXF_PATH.is_file(), "Y1A DXF fixture unavailable")
    def test_y1a_ordinary_braces_keep_existing_centerline_path(self):
        importer = DXFImporter(Y1A_DXF_PATH).read()

        result = importer.convert(
            layer_roles=_available_internal_layer_roles(
                importer,
                Y1A_LAYER_MAPPING,
            )
        )

        self.assertEqual(len(result.braces), 16)
        self.assertEqual(
            {member.recognition_method for member in result.braces},
            {"existing_centerline"},
        )
        self.assertFalse(
            any(
                member.recognition_method == "bim_block_whole_axis"
                for member in result.braces
            )
        )

    @unittest.skipUnless(Y29_DXF_PATH.is_file(), "Y29 DXF fixture unavailable")
    def test_y29_closed_outline_braces_keep_general_recognition_path(self):
        importer = DXFImporter(Y29_DXF_PATH).read()

        result = importer.convert(
            layer_roles=_available_internal_layer_roles(
                importer,
                Y29_LAYER_MAPPING,
            )
        )

        methods = [member.recognition_method for member in result.braces]
        self.assertEqual(len(methods), 32)
        self.assertEqual(methods.count("closed_outline_axis"), 31)
        self.assertEqual(methods.count("existing_centerline"), 1)
        self.assertNotIn("bim_block_whole_axis", methods)

class BlockMemberAmbiguityPolicyTests(unittest.TestCase):
    tolerances = GeometryTolerances()
    whole_span = 12000.0

    @staticmethod
    def source(primitives):
        return BlockMemberRecognitionInput(
            root_handle="AMBIGUITY-ROOT",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def rectangle(start, end, *, width=400.0, center_y=0.0):
        half_width = width / 2.0
        return BlockMemberPrimitive(
            (
                (start, center_y - half_width),
                (end, center_y - half_width),
                (end, center_y + half_width),
                (start, center_y + half_width),
            ),
            True,
            "LWPOLYLINE",
        )

    @classmethod
    def terminal_fragments(
        cls,
        support_length,
        *,
        whole_span=None,
        width=400.0,
        center_y=0.0,
    ):
        span = cls.whole_span if whole_span is None else whole_span
        half_support = support_length / 2.0
        return (
            cls.rectangle(0.0, half_support, width=width, center_y=center_y),
            cls.rectangle(
                span - half_support,
                span,
                width=width,
                center_y=center_y,
            ),
        )

    @staticmethod
    def rotate_to_y(primitives):
        return tuple(
            BlockMemberPrimitive(
                tuple((y, -x) for x, y in primitive.points),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in primitives
        )

    def recognize_conflict(self, horizontal_support, vertical_support):
        horizontal = self.terminal_fragments(horizontal_support)
        vertical = self.rotate_to_y(
            self.terminal_fragments(vertical_support)
        )
        return recognize_component_like_strut(
            self.source(horizontal + vertical),
            self.tolerances,
        )

    def test_equal_reliable_candidates_are_ambiguous(self):
        outcome = self.recognize_conflict(5000.0, 5000.0)

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)

    def test_reliable_49_percent_runner_still_makes_51_percent_winner_ambiguous(self):
        outcome = self.recognize_conflict(5100.0, 4900.0)

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_clear_reliable_winner_is_recognized(self):
        outcome = self.recognize_conflict(5300.0, 4700.0)

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.confidence, 0.53)

    def test_incomplete_runner_below_coverage_threshold_does_not_trigger_ambiguity(self):
        horizontal = self.terminal_fragments(5100.0)
        vertical = self.rotate_to_y(
            self.terminal_fragments(4900.0, whole_span=6000.0)
        )
        remote_detail = BlockMemberPrimitive(
            ((0.0, -12000.0), (80.0, -12000.0)),
            False,
            "LINE",
        )

        outcome = recognize_component_like_strut(
            self.source(horizontal + vertical + (remote_detail,)),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.confidence, 0.51)

    def test_equivalent_duplicate_does_not_hide_later_reliable_conflict(self):
        horizontal = self.terminal_fragments(5100.0, width=400.0)
        equivalent_duplicate = self.terminal_fragments(5100.0, width=460.0)
        vertical = self.rotate_to_y(self.terminal_fragments(4900.0))

        outcome = recognize_component_like_strut(
            self.source(horizontal + equivalent_duplicate + vertical),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )


class BlockMemberFinalOutcomeDeterminismTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives, *, root_handle="DETERMINISTIC-ROOT"):
        return BlockMemberRecognitionInput(
            root_handle=root_handle,
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def fragmented_polylines():
        return BlockMemberComponentClassificationTests.rectangles_along_x()

    @staticmethod
    def reindexed_polylines(primitives):
        outputs = []
        for index, primitive in enumerate(primitives):
            points = list(primitive.points)
            offset = (index + 1) % len(points)
            points = points[offset:] + points[:offset]
            points.reverse()
            outputs.append(
                BlockMemberPrimitive(
                    tuple(points),
                    True,
                    primitive.entity_type,
                )
            )
        return tuple(reversed(outputs))

    @staticmethod
    def reversed_line_contours(primitives):
        lines = []
        for primitive in primitives:
            points = tuple(primitive.points)
            for index, start in enumerate(points):
                end = points[(index + 1) % len(points)]
                lines.append(
                    BlockMemberPrimitive(
                        (end, start),
                        False,
                        "LINE",
                    )
                )
        return tuple(reversed(lines))

    def assert_same_recognized_outcome(self, expected, actual):
        self.assertIs(actual.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(actual.status, expected.status)
        self.assertEqual(actual.accepted_fragment_count, expected.accepted_fragment_count)
        self.assertAlmostEqual(
            actual.representative_width,
            expected.representative_width,
        )
        self.assertAlmostEqual(actual.confidence, expected.confidence)
        for actual_point, expected_point in zip(actual.whole_axis, expected.whole_axis):
            self.assertAlmostEqual(actual_point[0], expected_point[0])
            self.assertAlmostEqual(actual_point[1], expected_point[1])

    def test_equivalent_geometry_permutations_preserve_recognized_final_outcome(self):
        base = self.fragmented_polylines()
        expected = recognize_component_like_strut(
            self.source(base),
            self.tolerances,
        )
        variants = (
            tuple(reversed(base)),
            self.reindexed_polylines(base),
            self.reversed_line_contours(base),
            base + tuple(reversed(base)),
        )

        self.assertIs(expected.status, BlockMemberRecognitionStatus.RECOGNIZED)
        for variant in variants:
            with self.subTest(primitive_count=len(variant)):
                actual = recognize_component_like_strut(
                    self.source(variant),
                    self.tolerances,
                )
                self.assert_same_recognized_outcome(expected, actual)

    def test_equivalent_conflict_permutation_preserves_ambiguous_status(self):
        horizontal = self.fragmented_polylines()
        vertical = BlockMemberComponentClassificationTests.rotate_to_y(horizontal)
        expected = recognize_component_like_strut(
            self.source(horizontal + vertical),
            self.tolerances,
        )
        permuted = self.reindexed_polylines(horizontal + vertical)
        actual = recognize_component_like_strut(
            self.source(permuted),
            self.tolerances,
        )

        self.assertIs(expected.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(actual.status, expected.status)
        self.assertEqual(actual.diagnostic_code, expected.diagnostic_code)

    def test_equivalent_ordinary_geometry_preserves_not_applicable_status(self):
        ordinary = (
            BlockMemberPrimitive(((0.0, 0.0), (1800.0, 250.0)), False, "LINE"),
            BlockMemberPrimitive(((500.0, -600.0), (750.0, 1600.0)), False, "LINE"),
            BlockMemberPrimitive(((2300.0, 850.0), (3050.0, 1200.0)), False, "LINE"),
        )
        reversed_geometry = tuple(
            BlockMemberPrimitive(
                tuple(reversed(primitive.points)),
                primitive.closed,
                primitive.entity_type,
            )
            for primitive in reversed(ordinary)
        )

        first = recognize_component_like_strut(
            self.source(ordinary),
            self.tolerances,
        )
        second = recognize_component_like_strut(
            self.source(reversed_geometry),
            self.tolerances,
        )

        self.assertIs(first.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)
        self.assertEqual(second.status, first.status)


class Y05S10OutlineTopologyIntegrationTests(unittest.TestCase):
    def test_importer_uses_connected_outer_contour_axis_width_and_material(self):
        document = _new_document()
        _add_y05_s10_walers(document)
        insert = _add_y05_s10_insert(document)

        result = _convert_document(
            document,
            material_specs=(
                {"Usage": "支撐", "Spec": "H350x350"},
                {"Usage": "支撐", "Spec": "H400x400"},
            ),
        )

        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assertAlmostEqual(member.start[0], -15498.5)
        self.assertAlmostEqual(member.start[1], -23550.05)
        self.assertAlmostEqual(member.end[0], -15498.5)
        self.assertAlmostEqual(member.end[1], 8450.0)
        self.assertAlmostEqual(member.source_width, 350.0)
        self.assertEqual(member.material_spec, "H350x350")
        self.assertEqual(member.material_spec_source, "auto_width")
        self.assertFalse(
            any(
                message.code == "AMBIGUOUS_CENTERLINE"
                and insert.dxf.handle in message.source_handles
                for message in result.messages
            )
        )

    def test_unique_axis_with_unknown_envelope_width_does_not_guess_material(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        block = document.blocks.new("UNKNOWN_WIDTH_TOPOLOGY_STRUT")
        for width, center_y in ((500.0, -25.0), (480.0, 25.0)):
            half_width = width / 2.0
            block.add_lwpolyline(
                (
                    (0.0, center_y - half_width),
                    (12000.0, center_y - half_width),
                    (12000.0, center_y + half_width),
                    (0.0, center_y + half_width),
                ),
                close=True,
            )
        insert = document.modelspace().add_blockref(
            block.name,
            (0.0, 0.0),
            dxfattribs={"layer": STRUT_LAYER},
        )

        result = _convert_document(
            document,
            material_specs=(
                {"Usage": "支撐", "Spec": "H500x500"},
                {"Usage": "支撐", "Spec": "H480x480"},
            ),
        )

        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assertEqual(member.start, (0.0, 0.0))
        self.assertEqual(member.end, (12000.0, 0.0))
        self.assertEqual(member.source_width, 0.0)
        self.assertEqual(member.material_spec, "")
        self.assertEqual(member.material_spec_source, "")

    def test_single_400_and_500_envelopes_keep_existing_material_width_flow(self):
        for width in (400.0, 500.0):
            with self.subTest(width=width):
                document = _new_document()
                _add_horizontal_strut_walers(document)
                block = document.blocks.new(f"WIDTH_{int(width)}_STRUT")
                _add_rectangle(block, 0.0, 12000.0, width)
                document.modelspace().add_blockref(
                    block.name,
                    (0.0, 0.0),
                    dxfattribs={"layer": STRUT_LAYER},
                )
                spec = f"H{int(width)}x{int(width)}"

                result = _convert_document(
                    document,
                    material_specs=({"Usage": "支撐", "Spec": spec},),
                )

                self.assertEqual(len(result.struts), 1)
                self.assertAlmostEqual(result.struts[0].source_width, width)
                self.assertEqual(result.struts[0].material_spec, spec)


class Y05S2BlockMemberRegressionTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    def test_root_957_characterizes_local_and_whole_root_candidates(self):
        source = _y05_s2_recognition_source()
        fragments = _extract_fragment_axes(source.primitives, self.tolerances)
        candidates = _component_candidates(
            source,
            fragments,
            self.tolerances,
        )
        whole_root_candidates = _whole_root_envelope_candidates(
            source,
            self.tolerances,
        )
        source_only_outcome = recognize_component_like_strut(
            source,
            self.tolerances,
        )

        self.assertEqual(len(source.primitives), 54)
        self.assertEqual(len(fragments), 27)
        self.assertGreaterEqual(len(candidates), 2)
        self.assertAlmostEqual(candidates[0].evidence_ratio, 0.907178718, places=8)
        self.assertAlmostEqual(candidates[1].evidence_ratio, 0.873110802, places=8)
        self.assertAlmostEqual(
            candidates[0].evidence_ratio - candidates[1].evidence_ratio,
            0.034067916,
            places=8,
        )
        self.assertGreater(
            candidates[0].evidence_ratio - candidates[1].evidence_ratio,
            self.tolerances.ambiguous_candidate_score_delta,
        )

        self.assertAlmostEqual(candidates[0].axis[0][0], -53379.0, places=6)
        self.assertAlmostEqual(candidates[0].representative_width, 204.001046, places=6)
        self.assertGreaterEqual(len(whole_root_candidates), 1)
        self.assertAlmostEqual(
            whole_root_candidates[0].axis[0][0],
            -53469.5,
            places=6,
        )
        self.assertAlmostEqual(
            whole_root_candidates[0].representative_width,
            350.0,
            places=6,
        )

        self.assertIs(
            source_only_outcome.status,
            BlockMemberRecognitionStatus.RECOGNIZED,
        )
        self.assertAlmostEqual(
            source_only_outcome.whole_axis[0][0],
            -53379.0,
            places=6,
        )
        whole_axis_length = math.dist(*source_only_outcome.whole_axis)
        self.assertAlmostEqual(whole_axis_length, 18900.0, places=6)

        legacy_partial_axis = (
            (-53379.0, -3488.368),
            (-53379.0, 3489.368),
        )
        self.assertNotAlmostEqual(
            whole_axis_length,
            math.dist(*legacy_partial_axis),
            delta=1.0,
        )
        self.assertNotEqual(source_only_outcome.whole_axis, legacy_partial_axis)

    def test_importer_uses_y05_s2_whole_axis_instead_of_local_pair(self):
        document = _new_document()
        _add_y05_s2_walers(document)
        insert = _add_y05_s2_insert(document)

        result = _convert_document(document)

        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertEqual(member.recognition_method, "bim_block_whole_axis")
        self.assertAlmostEqual(member.start[0], -53469.5, places=6)
        self.assertAlmostEqual(member.start[1], -9450.0, places=6)
        self.assertAlmostEqual(member.end[0], -53469.5, places=6)
        self.assertAlmostEqual(member.end[1], 9450.0, places=6)
        self.assertAlmostEqual(member.source_width, 350.0, places=6)
        self.assertAlmostEqual(math.dist(member.start, member.end), 18900.0, places=6)
        self.assertEqual(len(member.line_candidates), 1)
        self.assertEqual(
            member.line_candidates[0].source,
            "bim_block_whole_axis",
        )
        self.assertNotAlmostEqual(
            math.dist(member.start, member.end),
            6977.736,
            delta=1.0,
        )
        self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))


class BlockMemberWholeAxisReconstructionTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives):
        return BlockMemberRecognitionInput(
            root_handle="WHOLE-AXIS-ROOT",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def rectangle(start, end):
        return BlockMemberOrientationClusteringTests.rectangle(start, end)

    def test_large_interior_gaps_still_produce_one_supported_whole_axis(self):
        primitives = (
            self.rectangle(250.0, 1800.0),
            self.rectangle(4200.0, 5600.0),
            self.rectangle(8900.0, 11750.0),
        )

        outcome = recognize_component_like_strut(
            self.source(primitives),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((250.0, 0.0), (11750.0, 0.0)))

    def test_local_three_meter_pair_does_not_truncate_twelve_meter_evidence(self):
        local_pair = (
            BlockMemberPrimitive(
                ((4500.0, -200.0), (7500.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((4500.0, 200.0), (7500.0, 200.0)),
                False,
                "LINE",
            ),
        )
        terminal_fragments = (
            self.rectangle(0.0, 2000.0),
            self.rectangle(10000.0, 12000.0),
        )

        outcome = recognize_component_like_strut(
            self.source(terminal_fragments + local_pair),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))

    def test_local_pair_without_supported_terminal_extent_fails(self):
        local_pair = (
            BlockMemberPrimitive(
                ((4500.0, -200.0), (7500.0, -200.0)),
                False,
                "LINE",
            ),
            BlockMemberPrimitive(
                ((4500.0, 200.0), (7500.0, 200.0)),
                False,
                "LINE",
            ),
        )
        transverse_terminal_details = (
            BlockMemberPrimitive(((0.0, -40.0), (0.0, 40.0)), False, "LINE"),
            BlockMemberPrimitive(
                ((12000.0, -40.0), (12000.0, 40.0)),
                False,
                "LINE",
            ),
        )

        outcome = recognize_component_like_strut(
            self.source(local_pair + transverse_terminal_details),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.FAILED)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_WHOLE_EXTENT_UNRELIABLE",
        )


class BlockMemberLegacyEvidenceTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def source(primitives):
        return BlockMemberRecognitionInput(
            root_handle="LEGACY-ROOT",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(primitives),
        )

    @staticmethod
    def general_candidate(primitives):
        group = _GeometryGroup(
            key="strut:LEGACY-ROOT",
            role="strut",
            layer=STRUT_LAYER,
            primitives=[
                _Primitive(
                    list(primitive.points),
                    primitive.closed,
                    primitive.entity_type,
                    "LEGACY-ROOT",
                    primitive.source_width,
                )
                for primitive in primitives
            ],
            handles={"LEGACY-ROOT"},
            entity_types={"INSERT", *(item.entity_type for item in primitives)},
            block_instances=[],
            root_handle="LEGACY-ROOT",
            root_entity_type="INSERT",
        )
        return _candidate_from_group(group, "strut", GeometryTolerances())

    @staticmethod
    def complete_outline():
        return BlockMemberPrimitive(
            (
                (0.0, -200.0),
                (12000.0, -200.0),
                (12000.0, 200.0),
                (0.0, 200.0),
            ),
            True,
            "LWPOLYLINE",
        )

    def test_full_span_legacy_sources_fall_back_with_existing_options_unchanged(self):
        cases = (
            (
                "explicit centerline",
                (
                    BlockMemberPrimitive(
                        ((0.0, 0.0), (12000.0, 0.0)),
                        False,
                        "LINE",
                    ),
                ),
                "existing_centerline",
                1,
            ),
            (
                "MLINE",
                (
                    BlockMemberPrimitive(
                        ((0.0, 0.0), (12000.0, 0.0)),
                        False,
                        "MLINE",
                        source_width=400.0,
                    ),
                ),
                "mline_center_path",
                3,
            ),
            (
                "closed outline",
                (self.complete_outline(),),
                "closed_outline_axis",
                3,
            ),
            (
                "parallel rails",
                (
                    BlockMemberPrimitive(
                        ((0.0, -200.0), (12000.0, -200.0)),
                        False,
                        "LINE",
                    ),
                    BlockMemberPrimitive(
                        ((0.0, 200.0), (12000.0, 200.0)),
                        False,
                        "LINE",
                    ),
                ),
                "parallel_edges_midline",
                3,
            ),
        )

        for label, primitives, expected_method, expected_option_count in cases:
            with self.subTest(label=label):
                outcome = recognize_component_like_strut(
                    self.source(primitives),
                    self.tolerances,
                )
                candidate, messages = self.general_candidate(primitives)

                self.assertIs(
                    outcome.status,
                    BlockMemberRecognitionStatus.NOT_APPLICABLE,
                )
                self.assertIsNotNone(candidate)
                self.assertEqual(candidate.recognition_method, expected_method)
                self.assertEqual(messages, [])
                self.assertEqual(
                    len(_engineering_line_candidates("strut", candidate)),
                    expected_option_count,
                )

    def test_full_span_outline_with_short_details_remains_legacy_evidence(self):
        details = tuple(
            BlockMemberPrimitive(
                ((station, -40.0), (station, 40.0)),
                False,
                "LINE",
            )
            for station in (3000.0, 6000.0, 9000.0)
        )

        outcome = recognize_component_like_strut(
            self.source((self.complete_outline(),) + details),
            self.tolerances,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.NOT_APPLICABLE)


class WalerConstrainedStrutRecognitionTests(unittest.TestCase):
    tolerances = GeometryTolerances()

    @staticmethod
    def s19_like_source():
        return BlockMemberRecognitionInput(
            root_handle="D4B",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(
                BlockMemberPrimitive(
                    ((x_coordinate, -23200.0), (x_coordinate, 8781.0)),
                    False,
                    "LINE",
                    source_handle="D4B",
                )
                for x_coordinate in (29326.5, 29495.5, 29507.5, 29676.5)
            ),
        )

    @staticmethod
    def s19_walers():
        return (
            WalerSpanReference(
                ("BOTTOM",),
                ((28000.0, -23200.0), (31000.0, -23200.0)),
            ),
            WalerSpanReference(
                ("TOP",),
                ((28000.0, 8781.0), (31000.0, 8781.0)),
            ),
        )

    @staticmethod
    def horizontal_source(stations, *, details=()):
        return BlockMemberRecognitionInput(
            root_handle="WHOLE-ROOT-TIER-2",
            root_entity_type="INSERT",
            role="strut",
            primitives=tuple(
                BlockMemberPrimitive(
                    ((100.0, station), (11900.0, station)),
                    False,
                    "LINE",
                    source_handle="WHOLE-ROOT-TIER-2",
                )
                for station in stations
            )
            + tuple(details),
        )

    @staticmethod
    def horizontal_walers(start=0.0, end=12000.0):
        return (
            WalerSpanReference(
                ("LEFT",),
                ((start, -2000.0), (start, 2000.0)),
            ),
            WalerSpanReference(
                ("RIGHT",),
                ((end, -2000.0), (end, 2000.0)),
            ),
        )

    def test_s19_like_root_uses_whole_envelope_not_left_local_pair(self):
        source = self.s19_like_source()

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.s19_walers(),
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(
            outcome.whole_axis,
            ((29501.5, -23200.0), (29501.5, 8781.0)),
        )
        self.assertAlmostEqual(outcome.representative_width, 350.0)
        self.assertNotAlmostEqual(outcome.whole_axis[0][0], 29411.0)
        self.assertNotAlmostEqual(outcome.representative_width, 186.5)
        self.assertEqual(
            outcome.selected_waler_source_handles,
            (("BOTTOM",), ("TOP",)),
        )

    def test_tier2_outer_rails_ignore_full_length_internal_rail(self):
        source = self.horizontal_source((-200.0, -6.0, 6.0, 200.0))

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.horizontal_walers(),
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 400.0)

    def test_tier2_short_outer_detail_does_not_expand_envelope(self):
        detail = BlockMemberPrimitive(
            ((3000.0, -300.0), (4000.0, -300.0)),
            False,
            "LINE",
            source_handle="WHOLE-ROOT-TIER-2",
        )
        source = self.horizontal_source(
            (-200.0, -6.0, 6.0, 200.0),
            details=(detail,),
        )

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.horizontal_walers(),
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(outcome.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(outcome.representative_width, 400.0)

    def test_two_complete_tier2_envelopes_remain_ambiguous(self):
        source = self.horizontal_source((-900.0, -500.0, 500.0, 900.0))
        candidates = _whole_root_envelope_candidates(source, self.tolerances)

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.horizontal_walers(),
        )

        self.assertTrue(candidates)
        self.assertTrue(
            all(
                candidate.representative_width
                <= self.tolerances.maximum_component_width_mm
                for candidate in candidates
            )
        )
        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(
            outcome.diagnostic_code,
            "BIM_BLOCK_CONFLICTING_WHOLE_AXES",
        )

    def test_waler_context_changes_only_longitudinal_terminal_span(self):
        source = self.horizontal_source((-200.0, -6.0, 6.0, 200.0))

        first = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.horizontal_walers(),
        )
        second = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=self.horizontal_walers(-500.0, 12500.0),
        )

        self.assertIs(first.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertIs(second.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertEqual(first.whole_axis, ((0.0, 0.0), (12000.0, 0.0)))
        self.assertAlmostEqual(second.whole_axis[0][0], -500.0, places=6)
        self.assertAlmostEqual(second.whole_axis[0][1], 0.0, places=6)
        self.assertAlmostEqual(second.whole_axis[1][0], 12500.0, places=6)
        self.assertAlmostEqual(second.whole_axis[1][1], 0.0, places=6)
        self.assertEqual(second.representative_width, first.representative_width)

    def test_waler_intersection_must_lie_on_each_finite_segment(self):
        source = self.s19_like_source()
        references = (
            WalerSpanReference(
                ("MISSED",),
                ((31050.0, -23200.0), (32000.0, -23200.0)),
            ),
            self.s19_walers()[1],
        )

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=references,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.FAILED)
        self.assertEqual(outcome.diagnostic_code, "BIM_BLOCK_WALER_SPAN_INCOMPLETE")
        self.assertEqual(outcome.selected_waler_source_handles, (("TOP",),))

    def test_two_nearly_equal_outward_walers_are_ambiguous(self):
        source = self.s19_like_source()
        references = (
            *self.s19_walers(),
            WalerSpanReference(
                ("BOTTOM-NEAR",),
                ((28000.0, -23210.0), (31000.0, -23210.0)),
            ),
        )

        outcome = recognize_component_like_strut(
            source,
            self.tolerances,
            waler_context=references,
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.AMBIGUOUS)
        self.assertEqual(outcome.diagnostic_code, "BIM_BLOCK_WALER_SPAN_AMBIGUOUS")
        self.assertIn(("BOTTOM",), outcome.selected_waler_source_handles)
        self.assertIn(("BOTTOM-NEAR",), outcome.selected_waler_source_handles)

    def test_router_passes_context_only_for_strut_root_insert(self):
        group = _group_from_recognition_source(self.s19_like_source())

        route = _route_component_like_strut_block(
            group,
            self.tolerances,
            waler_context=self.s19_walers(),
        )

        self.assertTrue(route.handled)
        self.assertIsNotNone(route.candidate)
        self.assertEqual(
            route.candidate.selected_waler_source_handles,
            (("BOTTOM",), ("TOP",)),
        )
        non_insert = replace(group, root_entity_type="LINE")
        self.assertFalse(
            _route_component_like_strut_block(
                non_insert,
                self.tolerances,
                waler_context=self.s19_walers(),
            ).handled
        )

    def test_context_builder_and_finalizer_preserve_waler_identity(self):
        left = _Candidate(
            (0.0, -1000.0),
            (0.0, 1000.0),
            "existing_centerline",
            False,
            0.0,
            1.0,
            WALER_LAYER,
            {"LEFT"},
            {"LINE"},
            [],
            {"waler:LEFT"},
            [],
        )
        right = replace(
            left,
            start=(12000.0, -1000.0),
            end=(12000.0, 1000.0),
            handles={"RIGHT"},
            source_keys={"waler:RIGHT"},
        )
        context = _build_waler_span_context((left, right))
        self.assertEqual(
            tuple(item.source_handles for item in context),
            (("LEFT",), ("RIGHT",)),
        )
        strut = _Candidate(
            (100.0, 0.0),
            (11900.0, 0.0),
            "bim_block_whole_axis",
            True,
            400.0,
            1.0,
            STRUT_LAYER,
            {"ROOT"},
            {"INSERT"},
            [],
            {"strut:ROOT"},
            [],
            recognized_axis=((100.0, 0.0), (11900.0, 0.0)),
            selected_waler_source_handles=(("LEFT",), ("RIGHT",)),
        )
        candidates = {"waler": [left, right], "strut": [strut]}

        messages = _finalize_contextual_strut_waler_spans(
            candidates,
            self.tolerances,
        )

        self.assertEqual(messages, [])
        self.assertEqual(candidates["strut"][0].start, (0.0, 0.0))
        self.assertEqual(candidates["strut"][0].end, (12000.0, 0.0))
        self.assertEqual(
            candidates["strut"][0].selected_waler_source_handles,
            (("LEFT",), ("RIGHT",)),
        )

    def test_finalizer_fails_closed_when_selected_waler_identity_disappears(self):
        waler = _Candidate(
            (0.0, -1000.0),
            (0.0, 1000.0),
            "existing_centerline",
            False,
            0.0,
            1.0,
            WALER_LAYER,
            {"LEFT"},
            {"LINE"},
            [],
            {"waler:LEFT"},
            [],
        )
        strut = _Candidate(
            (0.0, 0.0),
            (12000.0, 0.0),
            "bim_block_whole_axis",
            True,
            400.0,
            1.0,
            STRUT_LAYER,
            {"ROOT"},
            {"INSERT"},
            [],
            {"strut:ROOT"},
            [],
            recognized_axis=((0.0, 0.0), (12000.0, 0.0)),
            selected_waler_source_handles=(("LEFT",), ("MISSING",)),
        )
        candidates = {"waler": [waler], "strut": [strut]}

        messages = _finalize_contextual_strut_waler_spans(
            candidates,
            self.tolerances,
        )

        self.assertEqual(candidates["strut"], [])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].code, "BIM_BLOCK_WALER_FINALIZE_FAILED")
        self.assertEqual(messages[0].source_handles, ("ROOT",))
        self.assertIn("MISSING", messages[0].message)

    def test_incomplete_span_stays_one_unresolved_root_review_item(self):
        document = _new_document()
        waler = document.modelspace().add_line(
            (0.0, -1000.0),
            (0.0, 1000.0),
            dxfattribs={"layer": WALER_LAYER},
        )
        root = _add_fragmented_strut_insert(document)

        result = _convert_document(document)
        items = build_review_items(result, build_problem_records(result))
        unresolved = next(
            item
            for item in items
            if item.status == "unresolved"
            and root.dxf.handle in item.source_handles
        )

        self.assertEqual(unresolved.source_handles, (root.dxf.handle,))
        problem = next(
            item
            for item in unresolved.problems
            if item.code == "BIM_BLOCK_WALER_SPAN_INCOMPLETE"
        )
        self.assertIn(waler.dxf.handle, problem.description)

    def test_excluded_waler_is_not_visible_to_strut_context(self):
        document = _new_document()
        _add_horizontal_strut_walers(document)
        walers = tuple(document.modelspace().query(f'LINE[layer=="{WALER_LAYER}"]'))
        root = _add_fragmented_strut_insert(document)
        importer = DXFImporter("synthetic-bim-block.dxf")
        importer._document = document
        importer._source_fingerprint = "synthetic-bim-block-fingerprint"

        result = importer.convert(
            layer_roles={
                STRUT_LAYER: "strut",
                BRACE_LAYER: "brace",
                WALER_LAYER: "waler",
            },
            excluded_sources=(
                ExcludedSource("waler", (walers[1].dxf.handle,)),
            ),
        )

        self.assertFalse(
            any(root.dxf.handle in member.source_handles for member in result.struts)
        )
        failure = next(
            message
            for message in result.messages
            if message.code == "BIM_BLOCK_WALER_SPAN_INCOMPLETE"
            and root.dxf.handle in message.source_handles
        )
        self.assertNotIn(walers[1].dxf.handle, failure.message)

    def test_short_and_wrong_direction_details_do_not_move_s19_axis(self):
        source = self.s19_like_source()
        noisy = replace(
            source,
            primitives=source.primitives
            + (
                BlockMemberPrimitive(
                    ((29501.5, 100.0), (29501.5, 150.0)),
                    False,
                    "LINE",
                    source_handle="D4B",
                ),
                BlockMemberPrimitive(
                    ((29000.0, 0.0), (30000.0, 0.0)),
                    False,
                    "LINE",
                    source_handle="D4B",
                ),
                BlockMemberPrimitive(
                    ((31000.0, -23200.0), (31000.0, 8781.0)),
                    False,
                    "LINE",
                    source_handle="D4B",
                ),
            ),
        )

        outcome = recognize_component_like_strut(
            noisy,
            self.tolerances,
            waler_context=self.s19_walers(),
        )

        self.assertIs(outcome.status, BlockMemberRecognitionStatus.RECOGNIZED)
        self.assertAlmostEqual(outcome.whole_axis[0][0], 29501.5)
        self.assertAlmostEqual(outcome.whole_axis[1][0], 29501.5)


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF test asset unavailable")
class Y05StrutCenterAuthorityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.importer = DXFImporter(Y05_DXF_PATH).read()
        strut_layer = next(
            layer
            for layer, role in Y05_LAYER_ROLES.items()
            if role == "strut"
        )
        cls.groups = {
            group.root_handle: group
            for group in cls.importer._geometry_groups(
                "strut",
                strut_layer,
                cls.importer.entities_on_layer(strut_layer),
                [],
                [],
            )
        }
        cls.result = cls.importer.convert(layer_roles=Y05_LAYER_ROLES)

    def source(self, root_handle):
        return _recognition_source_from_group(self.groups[root_handle])

    def formal_member(self, root_handle):
        return next(
            member
            for member in self.result.struts
            if root_handle in member.source_handles
        )

    def test_d19_uses_tolerance_normalized_outer_contour(self):
        source = self.source("D19")
        outer_primitives = tuple(
            primitive
            for primitive in source.primitives
            if any(
                point[0] <= -5600.0 or point[0] >= -5400.0
                for point in primitive.points
            )
        )
        raw_outer_points = {
            point
            for primitive in outer_primitives
            for point in primitive.points
        }
        topology = _extract_topology_members(
            source.primitives,
            self.importer.tolerances,
        )
        member = self.formal_member("D19")

        self.assertEqual(len(raw_outer_points), 5)
        self.assertEqual(len(topology), 1)
        self.assertEqual(len(topology[0].points), 4)
        self.assertAlmostEqual(topology[0].axis[0][0], -5498.5, places=6)
        self.assertAlmostEqual(topology[0].axis[1][0], -5498.5, places=6)
        self.assertAlmostEqual(topology[0].width, 350.0, places=6)
        self.assertAlmostEqual(member.start[0], -5498.5, places=6)
        self.assertAlmostEqual(member.end[0], -5498.5, places=6)
        self.assertAlmostEqual(member.source_width, 350.0, places=6)

    def test_b05_and_957_have_mirrored_local_and_whole_root_candidates(self):
        characterized = {}
        for root_handle in ("957", "B05"):
            source = self.source(root_handle)
            fragments = _extract_fragment_axes(
                source.primitives,
                self.importer.tolerances,
            )
            local = _component_candidates(
                source,
                fragments,
                self.importer.tolerances,
            )
            whole = _whole_root_envelope_candidates(
                source,
                self.importer.tolerances,
            )
            characterized[root_handle] = (source, local, whole)

            self.assertEqual(len(source.primitives), 54)
            self.assertGreaterEqual(len(local), 2)
            self.assertGreaterEqual(len(whole), 1)
            self.assertAlmostEqual(local[0].representative_width, 204.001046, places=6)
            self.assertAlmostEqual(whole[0].representative_width, 350.0, places=6)

        _, negative_local, negative_whole = characterized["957"]
        _, positive_local, positive_whole = characterized["B05"]
        self.assertAlmostEqual(negative_local[0].axis[0][0], -53379.0, places=6)
        self.assertAlmostEqual(positive_local[0].axis[0][0], 53379.0, places=6)
        self.assertAlmostEqual(negative_whole[0].axis[0][0], -53469.5, places=6)
        self.assertAlmostEqual(positive_whole[0].axis[0][0], 53469.5, places=6)

    def test_b05_and_957_import_with_mirrored_outer_envelope_centers(self):
        negative = self.formal_member("957")
        positive = self.formal_member("B05")

        self.assertEqual(len(self.result.struts), 21)
        self.assertEqual(
            len({member.source_handles for member in self.result.struts}),
            21,
        )
        self.assertAlmostEqual(negative.start[0], -53469.5, places=6)
        self.assertAlmostEqual(negative.end[0], -53469.5, places=6)
        self.assertAlmostEqual(positive.start[0], 53469.5, places=6)
        self.assertAlmostEqual(positive.end[0], 53469.5, places=6)
        self.assertAlmostEqual(negative.source_width, 350.0, places=6)
        self.assertAlmostEqual(positive.source_width, 350.0, places=6)
        self.assertEqual({negative.from_waler, negative.to_waler}, {"W2", "W3"})
        self.assertEqual({positive.from_waler, positive.to_waler}, {"W5", "W6"})
        self.assertAlmostEqual(
            math.dist(negative.start, negative.end),
            math.dist(positive.start, positive.end),
            places=6,
        )


@unittest.skipUnless(Y05_DXF_PATH is not None, "Y05 DXF test asset unavailable")
class Y05S19WalerConstrainedRegressionTests(unittest.TestCase):
    def test_actual_d4b_characterizes_local_pair_then_imports_whole_section(self):
        importer = DXFImporter(Y05_DXF_PATH).read()
        strut_layer = next(
            layer
            for layer, role in Y05_LAYER_ROLES.items()
            if role == "strut"
        )
        groups = importer._geometry_groups(
            "strut",
            strut_layer,
            importer.entities_on_layer(strut_layer),
            [],
            [],
        )
        group = next(item for item in groups if item.root_handle == "D4B")
        longitudinal_stations = sorted(
            {
                round(start[0], 3)
                for primitive in group.primitives
                for start, end in primitive.segments()
                if abs(start[0] - end[0]) < 1e-6
                and abs(start[1] - end[1]) > 1000.0
            }
        )
        local_candidate, messages = _candidate_from_group(
            group,
            "strut",
            importer.tolerances,
        )

        self.assertEqual(
            longitudinal_stations,
            [29326.5, 29495.5, 29507.5, 29676.5],
        )
        self.assertEqual(messages, [])
        self.assertAlmostEqual(local_candidate.start[0], 29411.0, places=6)
        self.assertAlmostEqual(local_candidate.source_width, 186.5, places=2)

        result = importer.convert(layer_roles=Y05_LAYER_ROLES)
        member = next(
            item for item in result.struts if "D4B" in item.source_handles
        )

        self.assertAlmostEqual(member.start[0], 29501.5, places=6)
        self.assertAlmostEqual(member.end[0], 29501.5, places=6)
        self.assertAlmostEqual(member.source_width, 350.0, places=6)
        self.assertEqual({member.from_waler, member.to_waler}, {"W7", "W15"})
        self.assertNotAlmostEqual(member.start[0], 29411.0, places=3)


if __name__ == "__main__":
    unittest.main()
