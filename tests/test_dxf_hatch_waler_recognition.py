from __future__ import annotations

import tempfile
import unittest
import math
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.math import Vec3

from dxf_import.dialog import DXFImportDialog
from dxf_import.hatch_waler_recognition import (
    HatchBoundaryPath,
    HatchWalerSource,
    recognize_hatch_waler,
)
from dxf_import.importer import (
    DXFImporter,
    _segment_is_hatch_boundary_evidence,
    default_layer_mapping_for_file,
    import_dxf,
)
from dxf_import.material_recognition import (
    restore_manual_material_specs_from_debug,
    set_member_material_spec,
)
from dxf_import.models import DXFImportError, ExcludedSource, GeometryTolerances
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.validation import build_problem_records, build_review_items


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PRE_CHANGE_Y05_L_SHAPE_HANDLES = (
    "1648",
    "1649",
    "164A",
    "164B",
    "1651",
    "1652",
    "1653",
)


def _add_edge_hatch(
    modelspace: Any,
    points: tuple[tuple[float, float], ...],
    *,
    solid: bool = False,
    layer: str = "WALER",
) -> Any:
    hatch = modelspace.add_hatch(dxfattribs={"layer": layer})
    if solid:
        hatch.set_solid_fill()
    else:
        hatch.set_pattern_fill("ANSI31", scale=25.0)
    path = hatch.paths.add_edge_path()
    for start, end in zip(points, points[1:] + points[:1]):
        path.add_line(start, end)
    return hatch


def _add_polyline_hatch(
    modelspace: Any,
    points: tuple[tuple[float, float], ...],
    *,
    layer: str = "WALER",
) -> Any:
    hatch = modelspace.add_hatch(dxfattribs={"layer": layer})
    hatch.set_pattern_fill("ANSI32", scale=30.0)
    hatch.paths.add_polyline_path(points, is_closed=True)
    return hatch


def _add_outline_lines(
    modelspace: Any,
    points: tuple[tuple[float, float], ...],
    *,
    layer: str = "WALER",
) -> tuple[Any, ...]:
    return tuple(
        modelspace.add_line(start, end, dxfattribs={"layer": layer})
        for start, end in zip(points, points[1:] + points[:1])
    )


def _synthetic_hatch_corpus() -> tuple[Any, dict[str, Any]]:
    doc = ezdxf.new("R2010")
    for layer in ("WALER", "STRUT", "BRACE", "OTHER"):
        doc.layers.add(layer)
    modelspace = doc.modelspace()
    fixtures: dict[str, Any] = {}

    horizontal = ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0))
    vertical = ((12000.0, 800.0), (12800.0, 800.0), (12800.0, 12000.0), (12000.0, 12000.0))
    fixtures["patterned_edge"] = _add_edge_hatch(modelspace, horizontal)
    fixtures["solid_edge"] = _add_edge_hatch(
        modelspace,
        ((0.0, 2000.0), (10000.0, 2000.0), (10000.0, 2800.0), (0.0, 2800.0)),
        solid=True,
    )
    fixtures["polyline"] = _add_polyline_hatch(
        modelspace,
        ((0.0, 4000.0), (9000.0, 4000.0), (9000.0, 4800.0), (0.0, 4800.0)),
    )
    fixtures["touching_vertical"] = _add_edge_hatch(modelspace, vertical)
    fixtures["outline_lines"] = _add_outline_lines(modelspace, horizontal)

    hole = _add_edge_hatch(
        modelspace,
        ((0.0, 6000.0), (10000.0, 6000.0), (10000.0, 6800.0), (0.0, 6800.0)),
    )
    hole.paths.add_polyline_path(
        ((4500.0, 6200.0), (5500.0, 6200.0), (5500.0, 6600.0), (4500.0, 6600.0)),
        is_closed=True,
    )
    fixtures["hole"] = hole

    fixtures["l_shape"] = _add_edge_hatch(
        modelspace,
        (
            (0.0, 8000.0),
            (8000.0, 8000.0),
            (8000.0, 12000.0),
            (7200.0, 12000.0),
            (7200.0, 8800.0),
            (0.0, 8800.0),
        ),
    )
    multi = modelspace.add_hatch(dxfattribs={"layer": "WALER"})
    multi.set_pattern_fill("ANSI31", scale=25.0)
    multi.paths.add_polyline_path(
        ((0.0, 14000.0), (5000.0, 14000.0), (5000.0, 14800.0), (0.0, 14800.0)),
        is_closed=True,
    )
    multi.paths.add_polyline_path(
        ((7000.0, 14000.0), (12000.0, 14000.0), (12000.0, 14800.0), (7000.0, 14800.0)),
        is_closed=True,
    )
    fixtures["multi_exterior"] = multi
    fixtures["other_role"] = _add_edge_hatch(
        modelspace,
        ((0.0, 16000.0), (8000.0, 16000.0), (8000.0, 16800.0), (0.0, 16800.0)),
        layer="OTHER",
    )
    return doc, fixtures


def _edge_path_bounds(hatch: Any) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    for path in hatch.paths:
        for edge in getattr(path, "edges", ()):
            if not hasattr(edge, "start") or not hasattr(edge, "end"):
                continue
            points.extend(
                (
                    (float(edge.start.x), float(edge.start.y)),
                    (float(edge.end.x), float(edge.end.y)),
                )
            )
    return (
        min(point[0] for point in points),
        max(point[0] for point in points),
        min(point[1] for point in points),
        max(point[1] for point in points),
    )


def _boundary_path(
    points: tuple[tuple[float, float], ...],
    *,
    external: bool = False,
) -> HatchBoundaryPath:
    return HatchBoundaryPath(
        tuple(zip(points, points[1:] + points[:1])),
        is_external=external,
    )


def _pure_source(
    *paths: HatchBoundaryPath,
    handle: str = "HATCH-1",
) -> HatchWalerSource:
    return HatchWalerSource(handle, "WALER", tuple(paths))


def _rotate_points(
    points: tuple[tuple[float, float], ...],
    angle_degrees: float,
) -> tuple[tuple[float, float], ...]:
    angle = math.radians(angle_degrees)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return tuple(
        (x * cosine - y * sine, x * sine + y * cosine)
        for x, y in points
    )


def _save_and_import(
    document: Any,
    directory: str,
    *,
    layer_roles: dict[str, str] | None = None,
    excluded_sources: tuple[ExcludedSource, ...] = (),
    material_specs: tuple[dict[str, str], ...] = (),
):
    path = Path(directory) / "hatch-waler.dxf"
    document.saveas(path)
    return import_dxf(
        path,
        layer_roles=layer_roles
        or {
            "WALER": "waler",
            "STRUT": "strut",
        },
        excluded_sources=excluded_sources,
        material_specs=material_specs,
    )


class DxfHatchWalerCharacterizationTests(unittest.TestCase):
    def test_synthetic_fixture_corpus_preserves_required_hatch_topologies(self):
        doc, fixtures = _synthetic_hatch_corpus()

        self.assertEqual(fixtures["patterned_edge"].dxf.solid_fill, 0)
        self.assertEqual(fixtures["solid_edge"].dxf.solid_fill, 1)
        self.assertEqual(type(fixtures["patterned_edge"].paths[0]).__name__, "EdgePath")
        self.assertEqual(type(fixtures["polyline"].paths[0]).__name__, "PolylinePath")
        self.assertEqual(len(fixtures["hole"].paths), 2)
        self.assertEqual(len(fixtures["multi_exterior"].paths), 2)
        self.assertEqual(fixtures["patterned_edge"].dxf.layer, "WALER")
        self.assertEqual(fixtures["other_role"].dxf.layer, "OTHER")
        self.assertNotEqual(
            fixtures["patterned_edge"].dxf.handle,
            fixtures["touching_vertical"].dxf.handle,
        )
        self.assertEqual(
            _edge_path_bounds(fixtures["patterned_edge"]),
            (0.0, 12000.0, 0.0, 800.0),
        )
        self.assertEqual(
            _edge_path_bounds(fixtures["touching_vertical"]),
            (12000.0, 12800.0, 800.0, 12000.0),
        )
        self.assertEqual(len(fixtures["outline_lines"]), 4)
        self.assertEqual(len(tuple(doc.modelspace().query("HATCH"))), 8)

    def test_y05_hatches_become_four_independent_rc_walers_without_old_l_shape(self):
        paths = tuple(REPOSITORY_ROOT.glob("*Y05*.dxf"))
        self.assertEqual(len(paths), 1, "Repository should contain exactly one Y05 fixture")
        source_path = paths[0]
        doc = ezdxf.readfile(source_path)
        expected_bounds = {
            "1647": (22039.06742004146, 37800.0, -24000.0, -23200.0),
            "1650": (37000.0, 37800.0, -23200.0, -8900.0),
            "E65": (-37800.0, -22350.87965644063, -24000.0, -23200.0),
            "163D": (-37800.0, -37000.0, -23200.0, -8900.0),
        }
        expected_contact_lines = {
            "1647": ((22039.06742004146, -23200.0), (37800.0, -23200.0)),
            "1650": ((37000.0, -23200.0), (37000.0, -8900.0)),
            "E65": ((-37800.0, -23200.0), (-22350.87965644063, -23200.0)),
            "163D": ((-37000.0, -23200.0), (-37000.0, -8900.0)),
        }
        for handle, bounds in expected_bounds.items():
            with self.subTest(handle=handle):
                hatch = doc.entitydb[handle]
                self.assertEqual(hatch.dxftype(), "HATCH")
                self.assertEqual(hatch.dxf.layer, "圍令")
                self.assertEqual(hatch.dxf.associative, 0)
                self.assertEqual(len(hatch.paths), 1)
                self.assertEqual(type(hatch.paths[0]).__name__, "EdgePath")
                self.assertFalse(hatch.paths[0].source_boundary_objects)
                actual = _edge_path_bounds(hatch)
                for value, expected in zip(actual, bounds):
                    self.assertAlmostEqual(value, expected, places=3)
                self.assertAlmostEqual(
                    min(actual[1] - actual[0], actual[3] - actual[2]),
                    800.0,
                    places=3,
                )

        display_roles = default_layer_mapping_for_file(source_path)
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[label]
            for layer, label in display_roles.items()
        }
        result = import_dxf(source_path, layer_roles=layer_roles)
        by_handle = {
            waler.source_handles[0]: waler
            for waler in result.walers
            if len(waler.source_handles) == 1
            and waler.source_handles[0] in expected_bounds
        }
        self.assertEqual(set(by_handle), set(expected_bounds))
        for handle, waler in by_handle.items():
            with self.subTest(formal_waler=handle):
                actual_line = tuple(
                    sorted(
                        (round(point[0], 3), round(point[1], 3))
                        for point in (waler.start, waler.end)
                    )
                )
                expected_line = tuple(
                    sorted(
                        (round(point[0], 3), round(point[1], 3))
                        for point in expected_contact_lines[handle]
                    )
                )
                for actual, expected in zip(actual_line, expected_line):
                    self.assertAlmostEqual(actual[0], expected[0], places=3)
                    self.assertAlmostEqual(actual[1], expected[1], places=3)
                self.assertAlmostEqual(waler.source_width, 800.0, places=3)
                self.assertEqual(waler.material_spec, "RC")
                self.assertEqual(waler.material_spec_source, "auto_hatch")
                self.assertEqual(waler.source_entity_types, ("HATCH",))

        self.assertFalse(
            any(
                set(message.source_handles).intersection(
                    PRE_CHANGE_Y05_L_SHAPE_HANDLES
                )
                for message in result.messages
            )
        )
        debug_by_handle = {item.handle: item for item in result.entity_debug}
        self.assertTrue(
            all(
                debug_by_handle[handle].status == "boundary_evidence"
                for handle in PRE_CHANGE_Y05_L_SHAPE_HANDLES
            )
        )
        review_items = build_review_items(result)
        self.assertFalse(
            any(
                item.status == "unresolved"
                and set(item.source_handles).intersection(
                    PRE_CHANGE_Y05_L_SHAPE_HANDLES
                )
                for item in review_items
            )
        )


class HatchWalerPureRecognitionTests(unittest.TestCase):
    def test_800_mm_rectangle_is_recognized_without_global_width_gate(self):
        source = _pure_source(
            _boundary_path(
                ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
                external=True,
            )
        )

        result = recognize_hatch_waler(
            source,
            GeometryTolerances(maximum_component_width_mm=100.0),
        )

        self.assertEqual(result.status, "recognized")
        self.assertEqual(result.axis, ((0.0, 400.0), (12000.0, 400.0)))
        self.assertAlmostEqual(result.source_width, 800.0)
        self.assertEqual(
            result.boundary_lines,
            (
                ((0.0, 0.0), (12000.0, 0.0)),
                ((0.0, 800.0), (12000.0, 800.0)),
            ),
        )
        self.assertEqual(result.material_spec, "RC")
        self.assertEqual(result.material_spec_source, "auto_hatch")

    def test_edge_order_direction_and_cycle_start_are_deterministic(self):
        points = ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0))
        segments = list(zip(points, points[1:] + points[:1]))
        permuted = (
            tuple(reversed(segments[2])),
            tuple(reversed(segments[0])),
            tuple(reversed(segments[3])),
            tuple(reversed(segments[1])),
        )
        forward = recognize_hatch_waler(
            _pure_source(HatchBoundaryPath(tuple(segments), is_external=True))
        )
        changed = recognize_hatch_waler(
            _pure_source(HatchBoundaryPath(permuted, is_external=True))
        )

        self.assertEqual(changed, forward)

    def test_split_collinear_boundary_is_merged_before_strip_recognition(self):
        points = (
            (0.0, 0.0),
            (7000.0, 0.0),
            (12000.0, 0.0),
            (12000.0, 800.0),
            (0.0, 800.0),
        )
        result = recognize_hatch_waler(
            _pure_source(_boundary_path(points, external=True))
        )

        self.assertEqual(result.status, "recognized")
        self.assertEqual(result.axis, ((0.0, 400.0), (12000.0, 400.0)))

    def test_contained_hole_does_not_form_another_member(self):
        outer = _boundary_path(
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
            external=True,
        )
        hole = _boundary_path(
            ((5000.0, 200.0), (7000.0, 200.0), (7000.0, 600.0), (5000.0, 600.0))
        )

        result = recognize_hatch_waler(_pure_source(outer, hole))

        self.assertEqual(result.status, "recognized")
        self.assertEqual(result.axis, ((0.0, 400.0), (12000.0, 400.0)))

    def test_l_shape_and_square_cannot_create_a_straight_waler(self):
        l_shape = _boundary_path(
            (
                (0.0, 0.0),
                (8000.0, 0.0),
                (8000.0, 4000.0),
                (7200.0, 4000.0),
                (7200.0, 800.0),
                (0.0, 800.0),
            ),
            external=True,
        )
        square = _boundary_path(
            ((0.0, 0.0), (800.0, 0.0), (800.0, 800.0), (0.0, 800.0)),
            external=True,
        )

        for path in (l_shape, square):
            with self.subTest(path=path):
                result = recognize_hatch_waler(_pure_source(path))
                self.assertEqual(result.status, "failed")
                self.assertEqual(result.code, "HATCH_WALER_ENGINEERING_LINE_FAILED")
                self.assertIsNone(result.axis)

    def test_disconnected_exteriors_are_ambiguous(self):
        first = _boundary_path(
            ((0.0, 0.0), (5000.0, 0.0), (5000.0, 800.0), (0.0, 800.0))
        )
        second = _boundary_path(
            ((7000.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (7000.0, 800.0))
        )

        result = recognize_hatch_waler(_pure_source(first, second))

        self.assertEqual(result.status, "ambiguous")
        self.assertEqual(result.code, "HATCH_WALER_AMBIGUOUS_BOUNDARY")

    def test_unsupported_or_open_boundary_is_failed(self):
        unsupported = HatchBoundaryPath(
            (),
            is_external=True,
            unsupported_geometry=("ArcEdge",),
        )
        open_path = HatchBoundaryPath(
            (
                ((0.0, 0.0), (12000.0, 0.0)),
                ((12000.0, 0.0), (12000.0, 800.0)),
                ((12000.0, 800.0), (0.0, 800.0)),
            ),
            is_external=True,
        )

        unsupported_result = recognize_hatch_waler(_pure_source(unsupported))
        open_result = recognize_hatch_waler(_pure_source(open_path))

        self.assertEqual(unsupported_result.status, "failed")
        self.assertEqual(unsupported_result.code, "HATCH_WALER_UNSUPPORTED_BOUNDARY")
        self.assertEqual(open_result.status, "failed")
        self.assertEqual(open_result.code, "HATCH_WALER_BOUNDARY_INVALID")

    def test_rotated_rectangle_produces_the_same_whole_strip_axis(self):
        points = _rotate_points(
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
            30.0,
        )

        result = recognize_hatch_waler(
            _pure_source(_boundary_path(points, external=True))
        )

        expected = _rotate_points(((0.0, 400.0), (12000.0, 400.0)), 30.0)
        self.assertEqual(result.status, "recognized")
        self.assertIsNotNone(result.axis)
        for actual, wanted in zip(result.axis or (), expected):
            self.assertAlmostEqual(actual[0], wanted[0], places=6)
            self.assertAlmostEqual(actual[1], wanted[1], places=6)


class HatchWalerImporterAdapterTests(unittest.TestCase):
    @staticmethod
    def _base_document() -> tuple[Any, Any]:
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT", "OTHER"):
            document.layers.add(layer)
        return document, document.modelspace()

    def test_edge_and_polyline_hatches_route_only_from_waler_role(self):
        document, modelspace = self._base_document()
        lower = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        upper = _add_polyline_hatch(
            modelspace,
            (
                (0.0, 9200.0),
                (12000.0, 9200.0),
                (12000.0, 10000.0),
                (0.0, 10000.0),
            ),
        )
        ignored = _add_edge_hatch(
            modelspace,
            (
                (15000.0, 0.0),
                (23000.0, 0.0),
                (23000.0, 800.0),
                (15000.0, 800.0),
            ),
            layer="OTHER",
        )
        modelspace.add_line(
            (6000.0, 800.0),
            (6000.0, 9200.0),
            dxfattribs={"layer": "STRUT"},
        )

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(
                document,
                directory,
                layer_roles={
                    "WALER": "waler",
                    "STRUT": "strut",
                    "OTHER": "ignore",
                },
                material_specs=(
                    {"Usage": "圍令", "Spec": "H800x800"},
                ),
            )

        self.assertEqual(len(result.walers), 2)
        self.assertEqual(
            {waler.source_handles for waler in result.walers},
            {(lower.dxf.handle,), (upper.dxf.handle,)},
        )
        self.assertFalse(
            any(ignored.dxf.handle in waler.source_handles for waler in result.walers)
        )
        self.assertTrue(
            all(waler.source_entity_types == ("HATCH",) for waler in result.walers)
        )
        self.assertTrue(
            all(waler.recognition_method == "inner_boundary_line" for waler in result.walers)
        )
        self.assertEqual(
            {round((waler.start[1] + waler.end[1]) / 2.0) for waler in result.walers},
            {800, 9200},
        )
        self.assertTrue(all(abs(waler.source_width - 800.0) < 1e-6 for waler in result.walers))
        self.assertTrue(all(waler.material_spec == "RC" for waler in result.walers))
        self.assertTrue(
            all(waler.material_spec_source == "auto_hatch" for waler in result.walers)
        )
        project_rows = result.to_project_rows()
        self.assertTrue(
            all(row["material_spec"] == "RC" for row in project_rows["walers"])
        )
        self.assertNotIn("material_spec_source", project_rows["walers"][0])
        hatch_geometry = tuple(
            item
            for item in result.source_geometry
            if item.source_entity_type == "HATCH"
        )
        self.assertEqual(len(hatch_geometry), 8)
        self.assertEqual(
            {item.source_handle for item in hatch_geometry},
            {lower.dxf.handle, upper.dxf.handle},
        )
        hatch_debug = {
            item.handle: item
            for item in result.entity_debug
            if item.entity_type == "HATCH"
        }
        self.assertEqual(hatch_debug[lower.dxf.handle].status, "converted")
        self.assertEqual(hatch_debug[upper.dxf.handle].status, "converted")

    def test_hatch_boundary_adapter_applies_ocs_elevation_to_wcs(self):
        document, modelspace = self._base_document()
        hatch = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        hatch.dxf.extrusion = (0.0, 0.0, -1.0)
        hatch.dxf.elevation = (0.0, 0.0, 125.0)
        source_geometry = []

        source = DXFImporter._extract_hatch_waler_source(
            hatch,
            "WALER",
            source_geometry,
        )

        expected = hatch.ocs().to_wcs(Vec3(0.0, 0.0, 125.0))
        actual = source.paths[0].segments[0][0]
        self.assertAlmostEqual(actual[0], expected.x, places=6)
        self.assertAlmostEqual(actual[1], expected.y, places=6)
        self.assertEqual(len(source_geometry), 4)
        self.assertTrue(
            all(item.source_handle == hatch.dxf.handle for item in source_geometry)
        )
        outcome = recognize_hatch_waler(source)
        self.assertEqual(outcome.status, "recognized")

    def test_nonlinear_hatch_boundary_is_a_terminal_validation_failure(self):
        document, modelspace = self._base_document()
        valid = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        nonlinear = modelspace.add_hatch(dxfattribs={"layer": "WALER"})
        nonlinear.set_solid_fill()
        nonlinear.paths.add_edge_path().add_arc((18000.0, 4000.0), 800.0)
        modelspace.add_line(
            (6000.0, 800.0),
            (6000.0, 9000.0),
            dxfattribs={"layer": "STRUT"},
        )

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        self.assertTrue(any(valid.dxf.handle in item.source_handles for item in result.walers))
        failures = tuple(
            message
            for message in result.messages
            if nonlinear.dxf.handle in message.source_handles
        )
        self.assertEqual({message.code for message in failures}, {"HATCH_WALER_UNSUPPORTED_BOUNDARY"})
        self.assertFalse(
            any(nonlinear.dxf.handle in item.source_handles for item in result.walers)
        )

    def test_manual_material_override_and_replay_keep_existing_contract(self):
        document, modelspace = self._base_document()
        hatch = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        material_specs = (
            {"Usage": "圍令", "Spec": "RC"},
            {"Usage": "圍令", "Spec": "H350x350"},
        )

        with tempfile.TemporaryDirectory() as directory:
            base = _save_and_import(
                document,
                directory,
                material_specs=material_specs,
            )
            manual = set_member_material_spec(base, base.walers[0].id, "H350x350")
            rebuilt = _save_and_import(
                document,
                directory,
                material_specs=material_specs,
            )

        restored = restore_manual_material_specs_from_debug(
            rebuilt,
            manual.to_debug_dict(),
            material_specs,
        )

        self.assertEqual(base.walers[0].source_handles, (hatch.dxf.handle,))
        self.assertEqual(base.walers[0].material_spec, "RC")
        self.assertEqual(base.walers[0].material_spec_source, "auto_hatch")
        self.assertEqual(manual.walers[0].material_spec_source, "manual")
        self.assertEqual(restored.walers[0].material_spec, "H350x350")
        self.assertEqual(restored.walers[0].material_spec_source, "manual")


class HatchWalerBoundaryEvidenceTests(unittest.TestCase):
    @staticmethod
    def _base_document() -> tuple[Any, Any]:
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT"):
            document.layers.add(layer)
        return document, document.modelspace()

    def test_boundary_claim_requires_bidirectional_projection_coverage(self):
        settings = GeometryTolerances()
        split_boundary = (
            ((0.0, 0.0), (6000.0, 0.0)),
            ((6000.0, 0.0), (12000.0, 0.0)),
        )

        self.assertTrue(
            _segment_is_hatch_boundary_evidence(
                ((0.0, 0.0), (12000.0, 0.0)),
                split_boundary,
                settings,
            )
        )
        self.assertFalse(
            _segment_is_hatch_boundary_evidence(
                ((0.0, 0.0), (2000.0, 0.0)),
                split_boundary,
                settings,
            )
        )
        self.assertFalse(
            _segment_is_hatch_boundary_evidence(
                ((0.0, 100.0), (12000.0, 100.0)),
                split_boundary,
                settings,
            )
        )
        self.assertFalse(
            _segment_is_hatch_boundary_evidence(
                ((6000.0, -1000.0), (6000.0, 1000.0)),
                split_boundary,
                settings,
            )
        )

    def test_equivalent_line_and_polyline_outlines_are_preview_evidence_only(self):
        document, modelspace = self._base_document()
        lower_points = (
            (0.0, 0.0),
            (12000.0, 0.0),
            (12000.0, 800.0),
            (0.0, 800.0),
        )
        upper_points = (
            (0.0, 9200.0),
            (12000.0, 9200.0),
            (12000.0, 10000.0),
            (0.0, 10000.0),
        )
        lower_hatch = _add_edge_hatch(modelspace, lower_points)
        upper_hatch = _add_polyline_hatch(modelspace, upper_points)
        outline_lines = _add_outline_lines(modelspace, lower_points)
        outline_polyline = modelspace.add_lwpolyline(
            upper_points,
            close=True,
            dxfattribs={"layer": "WALER"},
        )
        partial = modelspace.add_line(
            (0.0, 0.0),
            (2000.0, 0.0),
            dxfattribs={"layer": "WALER"},
        )
        unrelated = modelspace.add_line(
            (0.0, 15000.0),
            (12000.0, 15000.0),
            dxfattribs={"layer": "WALER"},
        )
        modelspace.add_line(
            (6000.0, 800.0),
            (6000.0, 9200.0),
            dxfattribs={"layer": "STRUT"},
        )

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        member_handles = {
            handle
            for waler in result.walers
            for handle in waler.source_handles
        }
        self.assertIn(lower_hatch.dxf.handle, member_handles)
        self.assertIn(upper_hatch.dxf.handle, member_handles)
        self.assertIn(partial.dxf.handle, member_handles)
        self.assertIn(unrelated.dxf.handle, member_handles)
        claimed_handles = {
            *(entity.dxf.handle for entity in outline_lines),
            outline_polyline.dxf.handle,
        }
        self.assertTrue(claimed_handles.isdisjoint(member_handles))
        debug_by_handle = {item.handle: item for item in result.entity_debug}
        self.assertTrue(
            all(
                debug_by_handle[handle].status == "boundary_evidence"
                for handle in claimed_handles
            )
        )

    def test_failed_and_excluded_hatches_still_claim_equivalent_outlines(self):
        l_shape = (
            (0.0, 0.0),
            (8000.0, 0.0),
            (8000.0, 4000.0),
            (7200.0, 4000.0),
            (7200.0, 800.0),
            (0.0, 800.0),
        )
        document, modelspace = self._base_document()
        invalid_hatch = _add_edge_hatch(modelspace, l_shape)
        invalid_outline = _add_outline_lines(modelspace, l_shape)
        valid_points = (
            (12000.0, 0.0),
            (24000.0, 0.0),
            (24000.0, 800.0),
            (12000.0, 800.0),
        )
        excluded_hatch = _add_edge_hatch(modelspace, valid_points)
        excluded_outline = _add_outline_lines(modelspace, valid_points)

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(
                document,
                directory,
                layer_roles={"WALER": "waler", "STRUT": "strut"},
            )
            excluded_result = _save_and_import(
                document,
                directory,
                layer_roles={"WALER": "waler", "STRUT": "strut"},
                excluded_sources=(
                    ExcludedSource("waler", (excluded_hatch.dxf.handle,)),
                ),
            )

        invalid_line_handles = {entity.dxf.handle for entity in invalid_outline}
        self.assertTrue(
            any(
                message.code == "HATCH_WALER_ENGINEERING_LINE_FAILED"
                and message.source_handles == (invalid_hatch.dxf.handle,)
                for message in result.messages
            )
        )
        self.assertFalse(
            any(
                invalid_line_handles.intersection(message.source_handles)
                for message in result.messages
            )
        )
        excluded_line_handles = {entity.dxf.handle for entity in excluded_outline}
        excluded_member_handles = {
            handle
            for waler in excluded_result.walers
            for handle in waler.source_handles
        }
        self.assertNotIn(excluded_hatch.dxf.handle, excluded_member_handles)
        self.assertTrue(excluded_line_handles.isdisjoint(excluded_member_handles))
        debug_by_handle = {item.handle: item for item in excluded_result.entity_debug}
        self.assertTrue(
            all(
                debug_by_handle[handle].status == "boundary_evidence"
                for handle in excluded_line_handles
            )
        )

    def test_ambiguous_hatch_still_claims_both_equivalent_exteriors(self):
        document, modelspace = self._base_document()
        first = (
            (0.0, 0.0),
            (5000.0, 0.0),
            (5000.0, 800.0),
            (0.0, 800.0),
        )
        second = (
            (7000.0, 0.0),
            (12000.0, 0.0),
            (12000.0, 800.0),
            (7000.0, 800.0),
        )
        hatch = modelspace.add_hatch(dxfattribs={"layer": "WALER"})
        hatch.set_solid_fill()
        hatch.paths.add_polyline_path(first, is_closed=True)
        hatch.paths.add_polyline_path(second, is_closed=True)
        outlines = (*_add_outline_lines(modelspace, first), *_add_outline_lines(modelspace, second))

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        self.assertTrue(
            any(
                message.code == "HATCH_WALER_AMBIGUOUS_BOUNDARY"
                and message.source_handles == (hatch.dxf.handle,)
                for message in result.messages
            )
        )
        outline_handles = {entity.dxf.handle for entity in outlines}
        self.assertFalse(
            any(
                outline_handles.intersection(waler.source_handles)
                for waler in result.walers
            )
        )
        debug_by_handle = {item.handle: item for item in result.entity_debug}
        self.assertTrue(
            all(
                debug_by_handle[handle].status == "boundary_evidence"
                for handle in outline_handles
            )
        )

    def test_touching_hatches_remain_two_source_units_and_general_walers_are_unchanged(self):
        document, modelspace = self._base_document()
        horizontal_points = (
            (0.0, 0.0),
            (12000.0, 0.0),
            (12000.0, 800.0),
            (0.0, 800.0),
        )
        vertical_points = (
            (12000.0, 800.0),
            (12800.0, 800.0),
            (12800.0, 12000.0),
            (12000.0, 12000.0),
        )
        horizontal = _add_edge_hatch(modelspace, horizontal_points)
        vertical = _add_edge_hatch(modelspace, vertical_points)
        _add_outline_lines(modelspace, horizontal_points)
        _add_outline_lines(modelspace, vertical_points)
        ordinary = modelspace.add_line(
            (20000.0, 0.0),
            (30000.0, 0.0),
            dxfattribs={"layer": "WALER"},
        )

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        hatch_members = tuple(
            waler
            for waler in result.walers
            if waler.source_entity_types == ("HATCH",)
        )
        self.assertEqual(len(hatch_members), 2)
        self.assertEqual(
            {waler.source_handles for waler in hatch_members},
            {(horizontal.dxf.handle,), (vertical.dxf.handle,)},
        )
        self.assertTrue(
            any(ordinary.dxf.handle in waler.source_handles for waler in result.walers)
        )

    def test_line_polyline_and_mline_walers_without_hatch_keep_general_route(self):
        document, modelspace = self._base_document()
        line = modelspace.add_line(
            (0.0, 0.0),
            (12000.0, 0.0),
            dxfattribs={"layer": "WALER"},
        )
        polyline = modelspace.add_lwpolyline(
            ((0.0, 5000.0), (12000.0, 5000.0)),
            dxfattribs={"layer": "WALER"},
        )
        mline = modelspace.add_mline(
            ((0.0, 10000.0), (12000.0, 10000.0)),
            dxfattribs={"layer": "WALER"},
        )

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        handles_by_type = {
            waler.source_entity_types: waler.source_handles
            for waler in result.walers
        }
        self.assertEqual(handles_by_type[("LINE",)], (line.dxf.handle,))
        self.assertEqual(handles_by_type[("LWPOLYLINE",)], (polyline.dxf.handle,))
        self.assertEqual(handles_by_type[("MLINE",)], (mline.dxf.handle,))


class HatchWalerReviewLifecycleTests(unittest.TestCase):
    @staticmethod
    def _base_document() -> tuple[Any, Any]:
        document = ezdxf.new("R2010")
        for layer in ("WALER", "STRUT"):
            document.layers.add(layer)
        return document, document.modelspace()

    def test_terminal_failure_builds_hatch_owned_unresolved_review_item(self):
        document, modelspace = self._base_document()
        points = (
            (0.0, 0.0),
            (8000.0, 0.0),
            (8000.0, 4000.0),
            (7200.0, 4000.0),
            (7200.0, 800.0),
            (0.0, 800.0),
        )
        hatch = _add_edge_hatch(modelspace, points)
        outline = _add_outline_lines(modelspace, points)

        with tempfile.TemporaryDirectory() as directory:
            result = _save_and_import(document, directory)

        records = build_problem_records(result)
        items = build_review_items(result, records)
        unresolved = next(
            item
            for item in items
            if item.status == "unresolved"
            and item.source_handles == (hatch.dxf.handle,)
        )
        self.assertEqual(unresolved.role, "waler")
        self.assertEqual(unresolved.source_layers, ("WALER",))
        self.assertEqual(unresolved.source_entity_types, ("HATCH",))
        self.assertEqual(
            {problem.code for problem in unresolved.problems},
            {"HATCH_WALER_ENGINEERING_LINE_FAILED"},
        )
        self.assertTrue(unresolved.problems[0].description)
        self.assertFalse(result.can_import)
        with self.assertRaises(DXFImportError):
            result.to_project_rows()
        outline_handles = {entity.dxf.handle for entity in outline}
        self.assertFalse(
            any(outline_handles.intersection(item.source_handles) for item in items)
        )

    def test_exclude_restore_pause_resume_and_fingerprint_use_hatch_identity(self):
        document, modelspace = self._base_document()
        hatch = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        _add_outline_lines(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        material_specs = ({"Usage": "圍令", "Spec": "RC"},)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review-hatch.dxf"
            document.saveas(path)
            importer = DXFImporter(path).read()
            world = importer.convert(
                layer_roles={"WALER": "waler", "STRUT": "strut"},
                material_specs=material_specs,
            )
            workflow = DXFReviewWorkflow(
                importer,
                path,
                initial_world_result=world,
                material_specs=material_specs,
            )
            recognized = next(
                item
                for item in workflow.review_items
                if item.status == "recognized"
                and item.source_handles == (hatch.dxf.handle,)
            )
            before = workflow.world_result

            exclusion_plan, restoring, identity = workflow.plan_source_exclusion_for_item(
                recognized
            )

            self.assertFalse(restoring)
            self.assertEqual(identity, f"waler:{hatch.dxf.handle}")
            self.assertIs(workflow.world_result, before)
            self.assertFalse(exclusion_plan.world_result.walers)
            workflow.commit_source_exclusion_plan(exclusion_plan)
            excluded = next(
                item
                for item in workflow.review_items
                if item.status == "excluded"
                and item.source_handles == (hatch.dxf.handle,)
            )
            restore_plan, restoring, restored_identity = (
                workflow.plan_source_exclusion_for_item(excluded)
            )
            self.assertTrue(restoring)
            self.assertEqual(restored_identity, identity)
            workflow.commit_source_exclusion_plan(restore_plan)
            restored = workflow.world_result.walers[0]
            self.assertEqual(restored.source_handles, (hatch.dxf.handle,))
            self.assertEqual(restored.material_spec, "RC")
            self.assertEqual(restored.material_spec_source, "auto_hatch")

            state = workflow.serialize_review_state(
                layer_roles={"WALER": "waler", "STRUT": "strut"}
            )
            converted = state["converted"]["walers"][0]
            self.assertEqual(tuple(converted["source_handles"]), (hatch.dxf.handle,))
            self.assertEqual(tuple(converted["source_entity_types"]), ("HATCH",))
            self.assertEqual(converted["material_spec_source"], "auto_hatch")

            resumed_importer = DXFImporter(path).read()
            resumed_world = resumed_importer.convert(
                layer_roles={"WALER": "waler", "STRUT": "strut"},
                material_specs=material_specs,
            )
            resumed = DXFReviewWorkflow(
                resumed_importer,
                path,
                initial_state=state,
                resume_review=True,
                initial_world_result=resumed_world,
                material_specs=material_specs,
            )
            self.assertEqual(
                resumed.world_result.walers[0].source_handles,
                (hatch.dxf.handle,),
            )

            changed = ezdxf.readfile(path)
            changed.modelspace().add_line(
                (20000.0, 0.0),
                (25000.0, 0.0),
                dxfattribs={"layer": "WALER"},
            )
            changed.saveas(path)
            changed_importer = DXFImporter(path).read()
            with self.assertRaises(DXFImportError):
                DXFReviewWorkflow(
                    changed_importer,
                    path,
                    initial_state=state,
                    resume_review=True,
                )

    def test_duplicate_and_entity_permutations_have_deterministic_outcome(self):
        points = (
            (0.0, 0.0),
            (12000.0, 0.0),
            (12000.0, 800.0),
            (0.0, 800.0),
        )

        def build_variant(directory: str, reverse: bool):
            document, modelspace = self._base_document()
            ordered = tuple(reversed(points)) if reverse else points
            first = _add_edge_hatch(modelspace, ordered)
            second = _add_edge_hatch(modelspace, ordered[1:] + ordered[:1])
            segments = list(zip(points, points[1:] + points[:1]))
            if reverse:
                segments = [tuple(reversed(segment)) for segment in reversed(segments)]
            outlines = tuple(
                modelspace.add_line(start, end, dxfattribs={"layer": "WALER"})
                for start, end in segments
            )
            path = Path(directory) / ("reverse.dxf" if reverse else "forward.dxf")
            document.saveas(path)
            result = import_dxf(
                path,
                layer_roles={"WALER": "waler", "STRUT": "strut"},
            )
            return result, first, second, outlines

        with tempfile.TemporaryDirectory() as directory:
            forward, first, second, forward_outlines = build_variant(directory, False)
            reverse, _reverse_first, _reverse_second, reverse_outlines = build_variant(
                directory,
                True,
            )

        self.assertEqual(len(forward.walers), 1)
        self.assertEqual(len(reverse.walers), 1)
        self.assertEqual(
            set(forward.walers[0].source_handles),
            {first.dxf.handle, second.dxf.handle},
        )
        self.assertEqual(
            (
                forward.walers[0].start,
                forward.walers[0].end,
                forward.walers[0].source_width,
                forward.walers[0].material_spec,
                forward.walers[0].material_spec_source,
            ),
            (
                reverse.walers[0].start,
                reverse.walers[0].end,
                reverse.walers[0].source_width,
                reverse.walers[0].material_spec,
                reverse.walers[0].material_spec_source,
            ),
        )
        self.assertEqual(
            {message.code for message in forward.messages},
            {message.code for message in reverse.messages},
        )
        for result, outlines in (
            (forward, forward_outlines),
            (reverse, reverse_outlines),
        ):
            debug_by_handle = {item.handle: item for item in result.entity_debug}
            self.assertTrue(
                all(
                    debug_by_handle[entity.dxf.handle].status == "boundary_evidence"
                    for entity in outlines
                )
            )

    def test_hatch_entity_order_does_not_change_source_owned_geometry(self):
        document, modelspace = self._base_document()
        horizontal = _add_edge_hatch(
            modelspace,
            ((0.0, 0.0), (12000.0, 0.0), (12000.0, 800.0), (0.0, 800.0)),
        )
        vertical = _add_edge_hatch(
            modelspace,
            (
                (12000.0, 800.0),
                (12800.0, 800.0),
                (12800.0, 12000.0),
                (12000.0, 12000.0),
            ),
        )

        def source_signature(result):
            return {
                waler.source_handles: (
                    tuple(sorted((waler.start, waler.end))),
                    round(waler.source_width, 6),
                    waler.material_spec,
                    waler.material_spec_source,
                )
                for waler in result.walers
                if waler.source_entity_types == ("HATCH",)
            }

        with tempfile.TemporaryDirectory() as directory:
            first_path = Path(directory) / "entity-order-first.dxf"
            document.saveas(first_path)
            first = import_dxf(
                first_path,
                layer_roles={"WALER": "waler", "STRUT": "strut"},
            )

            modelspace.unlink_entity(horizontal)
            modelspace.add_entity(horizontal)
            second_path = Path(directory) / "entity-order-second.dxf"
            document.saveas(second_path)
            second = import_dxf(
                second_path,
                layer_roles={"WALER": "waler", "STRUT": "strut"},
            )

        self.assertEqual(
            set(source_signature(first)),
            {(horizontal.dxf.handle,), (vertical.dxf.handle,)},
        )
        self.assertEqual(source_signature(second), source_signature(first))


if __name__ == "__main__":
    unittest.main()
