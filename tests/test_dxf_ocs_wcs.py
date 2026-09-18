from __future__ import annotations

import math
from pathlib import Path
import tempfile
import unittest

import ezdxf
from ezdxf.disassemble import recursive_decompose

from dxf_import.geometry import _point
from dxf_import.importer import DXFImporter, import_dxf
from dxf_import.recognition import _GeometryGroup


class DXFImporterWorldGeometryTests(unittest.TestCase):
    def assert_points_almost_equal(self, actual, expected, *, places=6):
        self.assertEqual(len(actual), len(expected))
        for actual_point, expected_point in zip(actual, expected):
            self.assertAlmostEqual(actual_point[0], expected_point[0], places=places)
            self.assertAlmostEqual(actual_point[1], expected_point[1], places=places)

    @staticmethod
    def extract_source_geometry(entity):
        handle = str(entity.dxf.handle)
        group = _GeometryGroup(
            key=f"column:{handle}",
            role="column",
            layer="COLUMN",
            primitives=[],
            handles=set(),
            entity_types=set(),
            block_instances=[],
        )
        debug = []
        source_geometry = []
        DXFImporter("unused.dxf")._extract_entity(
            entity,
            group,
            debug,
            source_geometry,
            handle,
        )
        return group, tuple(source_geometry)

    @staticmethod
    def lwpolyline_insert(*, xscale, yscale, rotation=0.0):
        document = ezdxf.new("R2010")
        block = document.blocks.new("SECTION")
        local_points = ((-2.0, -1.0), (3.0, -1.0), (3.0, 2.0), (-2.0, 2.0))
        block.add_lwpolyline(local_points, close=True)
        insert = document.modelspace().add_blockref(
            "SECTION",
            (1200.0, -2300.0),
            dxfattribs={
                "layer": "COLUMN",
                "xscale": xscale,
                "yscale": yscale,
                "rotation": rotation,
            },
        )
        expected = tuple(
            _point(insert.matrix44().transform((x, y, 0.0)))
            for x, y in local_points
        )
        return insert, expected

    def assert_lwpolyline_insert_uses_wcs(
        self,
        *,
        xscale,
        yscale,
        rotation=0.0,
    ):
        insert, expected = self.lwpolyline_insert(
            xscale=xscale,
            yscale=yscale,
            rotation=rotation,
        )
        group, source_geometry = self.extract_source_geometry(insert)

        self.assertEqual(len(source_geometry), 1)
        self.assertEqual(source_geometry[0].source_entity_type, "LWPOLYLINE")
        self.assert_points_almost_equal(source_geometry[0].points, expected)
        self.assert_points_almost_equal(group.primitives[0].points, expected)

    def test_positive_scale_lwpolyline_insert_remains_in_wcs(self):
        self.assert_lwpolyline_insert_uses_wcs(xscale=2.0, yscale=3.0)

    def test_negative_x_scale_lwpolyline_insert_is_normalized_to_wcs(self):
        insert, expected = self.lwpolyline_insert(xscale=-2.0, yscale=3.0)
        virtual = next(insert.virtual_entities())
        self.assertAlmostEqual(virtual.dxf.extrusion.z, -1.0)

        group, source_geometry = self.extract_source_geometry(insert)

        self.assert_points_almost_equal(source_geometry[0].points, expected)
        self.assert_points_almost_equal(group.primitives[0].points, expected)

    def test_negative_x_scale_with_rotation_is_normalized_to_wcs(self):
        self.assert_lwpolyline_insert_uses_wcs(
            xscale=-2.0,
            yscale=3.0,
            rotation=30.0,
        )

    def test_negative_y_scale_with_rotation_is_normalized_to_wcs(self):
        self.assert_lwpolyline_insert_uses_wcs(
            xscale=2.0,
            yscale=-3.0,
            rotation=45.0,
        )

    def test_2d_and_3d_polylines_emit_wcs_vertices(self):
        for is_3d in (False, True):
            with self.subTest(is_3d=is_3d):
                document = ezdxf.new("R2010")
                block = document.blocks.new("POLYLINE_SECTION")
                local_points = ((0.0, 0.0), (4.0, 0.0), (4.0, 2.0))
                if is_3d:
                    block.add_polyline3d((*point, 0.0) for point in local_points)
                else:
                    block.add_polyline2d(local_points)
                insert = document.modelspace().add_blockref(
                    "POLYLINE_SECTION",
                    (500.0, 700.0),
                    dxfattribs={
                        "layer": "COLUMN",
                        "xscale": -5.0,
                        "yscale": 2.0,
                        "rotation": 30.0,
                    },
                )
                expected = tuple(
                    _point(insert.matrix44().transform((*point, 0.0)))
                    for point in local_points
                )

                group, source_geometry = self.extract_source_geometry(insert)

                self.assertEqual(source_geometry[0].source_entity_type, "POLYLINE")
                self.assert_points_almost_equal(source_geometry[0].points, expected)
                self.assert_points_almost_equal(group.primitives[0].points, expected)

    def test_solid_and_trace_emit_graphical_vertices_in_wcs(self):
        for entity_type in ("SOLID", "TRACE"):
            with self.subTest(entity_type=entity_type):
                document = ezdxf.new("R2010")
                block = document.blocks.new(f"{entity_type}_SECTION")
                local_points = (
                    (0.0, 0.0),
                    (4.0, 0.0),
                    (4.0, 2.0),
                    (0.0, 2.0),
                )
                if entity_type == "SOLID":
                    definition = block.add_solid(local_points)
                else:
                    definition = block.add_trace(local_points)
                insert = document.modelspace().add_blockref(
                    f"{entity_type}_SECTION",
                    (900.0, -600.0),
                    dxfattribs={
                        "layer": "COLUMN",
                        "xscale": -2.0,
                        "yscale": 3.0,
                        "rotation": 30.0,
                    },
                )
                expected = tuple(
                    _point(insert.matrix44().transform(vertex))
                    for vertex in definition.vertices()
                )

                group, source_geometry = self.extract_source_geometry(insert)

                self.assertEqual(source_geometry[0].source_entity_type, entity_type)
                self.assert_points_almost_equal(source_geometry[0].points, expected)
                self.assert_points_almost_equal(group.primitives[0].points, expected)

    def test_line_from_mirrored_rotated_insert_is_not_double_transformed(self):
        document = ezdxf.new("R2010")
        block = document.blocks.new("LINE_SECTION")
        definition = block.add_line((1.0, 2.0), (5.0, 7.0))
        insert = document.modelspace().add_blockref(
            "LINE_SECTION",
            (2000.0, 3000.0),
            dxfattribs={
                "layer": "COLUMN",
                "xscale": -2.0,
                "yscale": 3.0,
                "rotation": 30.0,
            },
        )
        expected = tuple(
            _point(insert.matrix44().transform(point))
            for point in (definition.dxf.start, definition.dxf.end)
        )

        group, source_geometry = self.extract_source_geometry(insert)

        self.assertEqual(source_geometry[0].source_entity_type, "LINE")
        self.assert_points_almost_equal(source_geometry[0].points, expected)
        self.assert_points_almost_equal(group.primitives[0].points, expected)

    def test_nested_insert_applies_block_transform_once_then_entity_ocs(self):
        document = ezdxf.new("R2010")
        leaf = document.blocks.new("LEAF_SECTION")
        leaf.add_lwpolyline(((0.0, 0.0), (10.0, 0.0), (10.0, 5.0)))
        parent = document.blocks.new("PARENT_SECTION")
        parent.add_blockref(
            "LEAF_SECTION",
            (20.0, 30.0),
            dxfattribs={"rotation": 15.0},
        )
        insert = document.modelspace().add_blockref(
            "PARENT_SECTION",
            (1000.0, 2000.0),
            dxfattribs={
                "layer": "COLUMN",
                "xscale": -2.0,
                "yscale": 2.0,
                "rotation": 30.0,
            },
        )
        leaf_entity = next(recursive_decompose((insert,)))
        expected = tuple(_point(point) for point in leaf_entity.vertices_in_wcs())

        group, source_geometry = self.extract_source_geometry(insert)

        self.assertEqual(len(source_geometry), 1)
        self.assert_points_almost_equal(source_geometry[0].points, expected)
        self.assert_points_almost_equal(group.primitives[0].points, expected)


class MirroredColumnImportTests(unittest.TestCase):
    def test_mirrored_column_uses_existing_association_and_double_support_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mirrored-column.dxf"
            document = ezdxf.new("R2010")
            for layer in ("WALER", "STRUT", "COLUMN"):
                document.layers.add(layer)
            model = document.modelspace()
            model.add_line((-2000.0, 0.0), (3000.0, 0.0), dxfattribs={"layer": "WALER"})
            model.add_line(
                (-2000.0, 10000.0),
                (3000.0, 10000.0),
                dxfattribs={"layer": "WALER"},
            )
            for center_x in (0.0, 1000.0):
                model.add_lwpolyline(
                    (
                        (center_x - 175.0, 0.0),
                        (center_x + 175.0, 0.0),
                        (center_x + 175.0, 10000.0),
                        (center_x - 175.0, 10000.0),
                    ),
                    close=True,
                    dxfattribs={"layer": "STRUT"},
                )
            block = document.blocks.new("H400")
            block.add_lwpolyline(
                ((-2.0, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)),
                close=True,
            )
            insert = model.add_blockref(
                "H400",
                (498.5, 5000.0),
                dxfattribs={
                    "layer": "COLUMN",
                    "xscale": -100.0,
                    "yscale": 100.0,
                },
            )
            document.saveas(path)

            result = import_dxf(
                path,
                layer_roles={
                    "WALER": "waler",
                    "STRUT": "strut",
                    "COLUMN": "column",
                },
            )

        self.assertEqual(len(result.columns), 1)
        column = result.columns[0]
        self.assertEqual(column.source_handles, (insert.dxf.handle,))
        self.assertAlmostEqual(column.reference_point[0], 498.5, places=6)
        self.assertAlmostEqual(column.reference_point[1], 5000.0, places=6)
        struts_by_x = {
            round((strut.start[0] + strut.end[0]) / 2): strut
            for strut in result.struts
        }
        nearer = struts_by_x[0]
        farther = struts_by_x[1000]
        self.assertEqual(column.associated_strut_id, nearer.id)
        self.assertAlmostEqual(column.association_distance, 498.5, places=6)
        pair = next(
            item
            for item in result.double_support_candidates
            if {item.first_strut_id, item.second_strut_id} == {nearer.id, farther.id}
        )
        self.assertTrue(pair.accepted)
        self.assertFalse(pair.ambiguous)
        self.assertIn(column.id, nearer.associated_columns)
        self.assertIn(column.id, farther.associated_columns)
        column_associations = [
            item
            for item in result.component_associations
            if item.component_id == column.id
            and item.component_role == "column"
        ]
        self.assertEqual(
            {item.strut_id for item in column_associations},
            {nearer.id, farther.id},
        )
        self.assertFalse(
            any(
                message.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
                and insert.dxf.handle in message.source_handles
                for message in result.messages
            )
        )


if __name__ == "__main__":
    unittest.main()
