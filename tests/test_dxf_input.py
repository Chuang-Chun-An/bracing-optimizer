import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from DXFinput import (
    CandidatePoint,
    CandidatePointStore,
    CandidateTreeAdapter,
    CoordinateSystem,
    DEFAULT_LAYER_MAPPING,
    DXFImportDialog,
    DXFImportError,
    GeometryTolerances,
    PreviewRenderer,
    PreviewScene,
    RenderDirty,
    RenderScheduler,
    SelectionController,
    SelectionState,
    Strut,
    Column,
    add_cad_candidate_points,
    associate_components_to_struts,
    apply_candidate_point_selection,
    apply_coordinate_system,
    build_problem_records,
    build_validation_overview,
    fit_window_geometry_to_work_areas,
    import_dxf,
    parse_coordinate_origin,
    read_dxf_layers,
    rectangle_centerline,
    select_engineering_line,
    set_cad_engineering_line,
    validate_candidate_point_pair,
)


LAYERS = ("WALER", "STRUT", "BRACE", "EMPTY")


class DXFInputRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.counter = 0

    def tearDown(self):
        self.temp_dir.cleanup()

    def new_doc(self):
        doc = ezdxf.new("R2010")
        for layer in LAYERS:
            doc.layers.add(layer)
        return doc

    def test_test_layer_defaults_are_exact_and_saved_selection_wins(self):
        self.assertEqual(
            DXFImportDialog.LAYER_USE_OPTIONS,
            (
                "圍令",
                "支撐",
                "斜撐",
                "中間柱",
                "托梁",
                "角撐",
                "輔助線",
                "忽略",
            ),
        )
        expected_defaults = {
            "ES-圍令L1H350x350": "圍令",
            "ES-LH350x350": "支撐",
            "ES-大斜撐_支撐350x350": "斜撐",
            "!T1 (站體)_角撐": "角撐",
            "ES-中間樁NO": "中間柱",
            "ES-C250x90": "托梁",
        }
        self.assertTrue(expected_defaults.items() <= DEFAULT_LAYER_MAPPING.items())
        self.assertEqual(
            DXFImportDialog._initial_layer_use("ES-LH350x350", {}),
            "支撐",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use(
                "ES-LH350x350",
                {"ES-LH350x350": "ignore"},
            ),
            "忽略",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use("ES-LH350x350-extra", {}),
            "忽略",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use("ES-中間樁NO", {}),
            "中間柱",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use("!T1 (站體)_角撐", {}),
            "角撐",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use("ES-C250x90", {}),
            "托梁",
        )
        self.assertEqual(
            DXFImportDialog._initial_layer_use(
                "Existing_Wall",
                {"Existing_Wall": "auxiliary"},
            ),
            "輔助線",
        )

    def convert(self, doc, *, tolerances=None):
        self.counter += 1
        path = Path(self.temp_dir.name) / f"case_{self.counter}.dxf"
        doc.saveas(path)
        result = import_dxf(
            path,
            waler_layer="WALER",
            strut_layer="STRUT",
            brace_layer="BRACE",
            tolerances=tolerances,
        )
        return result, path

    @staticmethod
    def add_horizontal_walers(model):
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})

    @staticmethod
    def add_vertical_walers(model):
        model.add_line((0, -200), (0, 1200), dxfattribs={"layer": "WALER"})
        model.add_line((1000, -200), (1000, 1200), dxfattribs={"layer": "WALER"})

    @staticmethod
    def add_default_strut_and_brace(model):
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})

    @staticmethod
    def outline_around(start, end, half_width=20):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        nx, ny = -dy / length * half_width, dx / length * half_width
        return [
            (start[0] + nx, start[1] + ny),
            (start[0] - nx, start[1] - ny),
            (end[0] - nx, end[1] - ny),
            (end[0] + nx, end[1] + ny),
        ]

    def test_reads_declared_layers_including_empty_layer(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, path = self.convert(doc)
        self.assertIn("EMPTY", read_dxf_layers(path))

    def test_remembered_preview_geometry_is_moved_back_from_disconnected_monitor(self):
        primary_only = ((0, 0, 1920, 1040),)
        self.assertEqual(
            fit_window_geometry_to_work_areas(
                "1100x800+2100+100",
                "1100x800+80+80",
                primary_only,
            ),
            "1100x800+820+100",
        )

    def test_remembered_preview_geometry_stays_on_an_active_second_monitor(self):
        dual_monitors = (
            (0, 0, 1920, 1040),
            (1920, 0, 3840, 1040),
        )
        self.assertEqual(
            fit_window_geometry_to_work_areas(
                "1100x800+2100+100",
                "1100x800+80+80",
                dual_monitors,
            ),
            "1100x800+2100+100",
        )

    def test_remembered_preview_geometry_supports_left_side_monitor(self):
        dual_monitors = (
            (-1920, 0, 0, 1040),
            (0, 0, 1920, 1040),
        )
        self.assertEqual(
            fit_window_geometry_to_work_areas(
                "1100x800-1800+100",
                "1100x800+80+80",
                dual_monitors,
            ),
            "1100x800-1800+100",
        )

    def test_preview_source_geometry_excludes_ignored_layers(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        model.add_line((5000, 5000), (6000, 5000), dxfattribs={"layer": "0"})
        result, _path = self.convert(doc)

        self.assertFalse(
            any(geometry.role == "ignore" for geometry in result.source_geometry)
        )
        visible = DXFImportDialog._preview_source_geometry(result)
        self.assertTrue(visible)
        self.assertTrue(all(geometry.role != "ignore" for geometry in visible))
        info = {item.name: item for item in result.layer_info}
        self.assertEqual(info["EMPTY"].entity_count, 0)

    def test_auxiliary_layer_is_preview_only_and_has_independent_visibility(self):
        doc = self.new_doc()
        doc.layers.add("AUXILIARY")
        doc.layers.add("IGNORED")
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        auxiliary_entity = model.add_line(
            (-500, 500),
            (1500, 500),
            dxfattribs={"layer": "AUXILIARY"},
        )
        ignored_entity = model.add_line(
            (5000, 5000),
            (6000, 5000),
            dxfattribs={"layer": "IGNORED"},
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"auxiliary_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "AUXILIARY": "auxiliary",
                "IGNORED": "ignore",
            },
        )

        self.assertEqual(result.layer_classification["AUXILIARY"], "auxiliary")
        self.assertEqual(result.selected_layers["auxiliary"], ("AUXILIARY",))
        self.assertEqual(result.source_entity_counts["auxiliary"], 1)
        auxiliary_geometry = tuple(
            geometry
            for geometry in result.source_geometry
            if geometry.role == "auxiliary"
        )
        self.assertEqual(len(auxiliary_geometry), 1)
        self.assertEqual(auxiliary_geometry[0].source_layer, "AUXILIARY")
        self.assertNotIn(
            str(ignored_entity.dxf.handle),
            {item.handle for item in result.entity_debug},
        )
        self.assertFalse(
            any(message.role == "auxiliary" for message in result.messages)
        )
        engineering_members = (
            *result.walers,
            *result.struts,
            *result.braces,
            *result.columns,
            *result.beams,
            *result.corner_braces,
        )
        self.assertNotIn(
            "AUXILIARY",
            {member.source_layer for member in engineering_members},
        )
        self.assertNotIn(
            str(auxiliary_entity.dxf.handle),
            {
                handle
                for member in engineering_members
                for handle in member.source_handles
            },
        )

        auxiliary_only = DXFImportDialog._visible_preview_source_geometry(
            result,
            show_source=False,
            show_auxiliary=True,
        )
        self.assertTrue(auxiliary_only)
        self.assertTrue(
            all(geometry.role == "auxiliary" for geometry in auxiliary_only)
        )
        engineering_only = DXFImportDialog._visible_preview_source_geometry(
            result,
            show_source=True,
            show_auxiliary=False,
        )
        self.assertTrue(engineering_only)
        self.assertTrue(
            all(geometry.role != "auxiliary" for geometry in engineering_only)
        )
        self.assertEqual(
            DXFImportDialog._visible_preview_source_geometry(
                result,
                show_source=False,
                show_auxiliary=False,
            ),
            (),
        )

        debug = result.to_debug_dict()
        self.assertIn(
            {"layer_name": "AUXILIARY", "layer_type": "auxiliary"},
            debug["layer_assignments"],
        )
        self.assertEqual(debug["summary"]["auxiliary_geometry"], 1)

    def test_rectangle_waler_and_four_line_waler_each_make_one_model(self):
        doc = self.new_doc()
        model = doc.modelspace()
        model.add_lwpolyline(
            [(0, -20), (1000, -20), (1000, 20), (0, 20)],
            close=True,
            dxfattribs={"layer": "WALER"},
        )
        upper = [(0, 980), (1000, 980), (1000, 1020), (0, 1020)]
        for start, end in zip(upper, upper[1:] + upper[:1]):
            model.add_line(start, end, dxfattribs={"layer": "WALER"})
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        self.assertEqual(len(result.walers), 2)
        self.assertTrue(all(not member.centerline_computed for member in result.walers))
        self.assertTrue(all(member.engineering_line_kind == "inner_line" for member in result.walers))
        self.assertEqual(
            {member.recognition_method for member in result.walers},
            {"inner_boundary_line"},
        )
        self.assertEqual(sorted(member.start[1] for member in result.walers), [20.0, 980.0])
        self.assertEqual(sorted(member.end[1] for member in result.walers), [20.0, 980.0])
        self.assertEqual(result.struts[0].start[1], 20.0)
        self.assertEqual(result.struts[0].end[1], 980.0)
        self.assertEqual(
            sorted(row["StartY"] for row in result.to_project_rows()["walers"]),
            [20.0, 980.0],
        )
        self.assertTrue(result.can_import)

    def test_existing_centerline_waler_is_preserved(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        self.assertEqual(len(result.walers), 2)
        self.assertTrue(all(member.recognition_method == "existing_inner_line" for member in result.walers))
        self.assertTrue(all(not member.centerline_computed for member in result.walers))

    def test_manual_waler_candidate_replaces_result_and_solver_row(self):
        doc = self.new_doc()
        model = doc.modelspace()
        model.add_lwpolyline(
            [(0, -20), (1000, -20), (1000, 20), (0, 20)],
            close=True,
            dxfattribs={"layer": "WALER"},
        )
        model.add_lwpolyline(
            [(0, 980), (1000, 980), (1000, 1020), (0, 1020)],
            close=True,
            dxfattribs={"layer": "WALER"},
        )
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        lower = min(result.walers, key=lambda member: member.start[1])
        self.assertEqual(len(lower.line_candidates), 3)
        self.assertEqual(lower.line_candidates[2].label, "中心線")
        self.assertEqual(lower.selected_candidate_id, "line_1")
        source_before = result.source_geometry

        corrected = select_engineering_line(result, lower.id, "line_2")
        corrected_lower = next(member for member in corrected.walers if member.id == lower.id)
        self.assertEqual(corrected_lower.selection_source, "manual_candidate_points")
        self.assertEqual(corrected_lower.selected_candidate_id, "line_2")
        self.assertEqual(corrected_lower.start[1], -20.0)
        self.assertEqual(corrected.source_geometry, source_before)
        solver_row = next(
            row
            for row in corrected.to_project_rows()["walers"]
            if row["WalerID"] == lower.id
        )
        self.assertEqual(solver_row["StartY"], -20.0)
        self.assertIn(
            "line_candidates",
            corrected.to_debug_dict()["converted"]["walers"][0],
        )

    def test_manual_strut_boundary_reconnects_and_respects_local_coordinates(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_vertical_walers(model)
        model.add_lwpolyline(
            [(0, 480), (1000, 480), (1000, 520), (0, 520)],
            close=True,
            dxfattribs={"layer": "STRUT"},
        )
        model.add_line((0, 100), (1000, 900), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        local_result = apply_coordinate_system(
            result,
            CoordinateSystem("local", 100.0, 200.0, "user_input"),
        )
        self.assertGreaterEqual(len(local_result.struts[0].line_candidates), 3)

        corrected = select_engineering_line(local_result, "S1", "line_2")
        member = corrected.struts[0]
        self.assertEqual(member.selection_source, "manual_candidate_points")
        self.assertTrue(member.from_waler and member.to_waler)
        self.assertEqual(member.local_start, corrected.coordinate_system.transform(member.world_start))
        row = corrected.to_project_rows()["struts"][0]
        self.assertEqual((row["StartX"], row["StartY"]), member.local_start)

    def test_cad_temp_line_becomes_selected_candidate_and_solver_geometry(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        source_before = result.source_geometry

        corrected = set_cad_engineering_line(
            result,
            "S1",
            (400.0, 0.0),
            (400.0, 1000.0),
        )
        member = corrected.struts[0]
        self.assertEqual(member.selected_candidate_id, "cad_manual_line")
        self.assertEqual(member.selection_source, "cad_manual")
        self.assertEqual(member.world_start, (400.0, 0.0))
        self.assertEqual(member.world_end, (400.0, 1000.0))
        self.assertEqual(corrected.source_geometry, source_before)
        self.assertEqual(
            corrected.to_project_rows()["struts"][0]["StartX"],
            400.0,
        )

    def test_candidate_points_have_recommended_and_selected_exact_endpoints(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)

        member = result.struts[0]
        self.assertGreaterEqual(len(member.candidate_points), 2)
        start = next(
            point
            for point in member.candidate_points
            if point.id == member.recommended_start_point_id
        )
        end = next(
            point
            for point in member.candidate_points
            if point.id == member.recommended_end_point_id
        )
        self.assertEqual(member.selected_start_point_id, start.id)
        self.assertEqual(member.selected_end_point_id, end.id)
        self.assertEqual(start.world_point, member.world_start)
        self.assertEqual(end.world_point, member.world_end)
        self.assertIn("start", start.recommended_for)
        self.assertIn("end", end.recommended_for)
        self.assertEqual(start.valid_for, ("start",))
        self.assertEqual(end.valid_for, ("end",))
        self.assertNotIn(
            end.id,
            {
                point.id
                for point in member.candidate_points
                if "start" in point.valid_for
            },
        )
        self.assertNotIn(
            start.id,
            {
                point.id
                for point in member.candidate_points
                if "end" in point.valid_for
            },
        )

    def test_candidate_local_coordinates_recalculate_from_world_without_double_origin(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        world_point = result.struts[0].candidate_points[0].world_point

        local = apply_coordinate_system(
            result,
            CoordinateSystem("local", 100.0, -200.0, "user_input"),
        )
        reapplied = apply_coordinate_system(
            local,
            CoordinateSystem("local", 100.0, -200.0, "user_input"),
        )
        expected = world_point[0] - 100.0, world_point[1] + 200.0
        self.assertEqual(local.struts[0].candidate_points[0].world_point, world_point)
        self.assertEqual(local.struts[0].candidate_points[0].local_point, expected)
        self.assertEqual(reapplied.struts[0].candidate_points[0].local_point, expected)

    def test_cad_candidates_stay_pending_until_explicit_apply(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        original_start = result.struts[0].world_start

        pending, start_id, end_id = add_cad_candidate_points(
            result,
            "S1",
            (400.0, 0.0),
            (400.0, 1000.0),
        )
        self.assertEqual(pending.struts[0].world_start, original_start)
        committed = apply_candidate_point_selection(
            pending,
            "S1",
            start_id,
            end_id,
            selection_source="cad_manual",
        )
        self.assertEqual(committed.struts[0].world_start, (400.0, 0.0))
        self.assertEqual(committed.struts[0].selection_source, "cad_manual")
        self.assertEqual(committed.to_project_rows()["struts"][0]["StartX"], 400.0)

    def test_replacing_cad_candidates_keeps_the_current_formal_endpoints(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        first_pending, first_start, first_end = add_cad_candidate_points(
            result,
            "S1",
            (400.0, 0.0),
            (400.0, 1000.0),
        )
        committed = apply_candidate_point_selection(
            first_pending,
            "S1",
            first_start,
            first_end,
            selection_source="cad_manual",
        )

        second_pending, _second_start, _second_end = add_cad_candidate_points(
            committed,
            "S1",
            (600.0, 0.0),
            (600.0, 1000.0),
        )
        member = second_pending.struts[0]
        self.assertEqual(member.world_start, (400.0, 0.0))
        point_ids = {point.id for point in member.candidate_points}
        self.assertIn(member.selected_start_point_id, point_ids)
        self.assertIn(member.selected_end_point_id, point_ids)

    def test_candidate_pair_validation_blocks_same_point(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        member = result.struts[0]
        messages = validate_candidate_point_pair(
            member,
            member.selected_start_point_id,
            member.selected_start_point_id,
        )
        self.assertEqual(messages[0].severity, "error")
        self.assertEqual(messages[0].code, "ZERO_LENGTH_CANDIDATE_LINE")

    def test_candidate_hit_test_uses_canvas_pixel_distance_and_keeps_overlap(self):
        hits = DXFImportDialog._preview_candidate_hits(
            (100.0, 100.0),
            (("P01", (104.0, 100.0)), ("P02", (106.0, 100.0))),
            tolerance_pixels=8.0,
        )
        self.assertEqual(hits, ("P01", "P02"))

    def test_preview_endpoint_hit_test_uses_visible_marker_pixels(self):
        hits = DXFImportDialog._preview_endpoint_hits(
            (100.0, 100.0),
            (("start", (106.0, 100.0)), ("end", (130.0, 100.0))),
            tolerance_pixels=12.0,
        )
        self.assertEqual(hits, ("start",))
        overlapping = DXFImportDialog._preview_endpoint_hits(
            (100.0, 100.0),
            (("start", (104.0, 100.0)), ("end", (106.0, 100.0))),
            tolerance_pixels=12.0,
        )
        self.assertEqual(overlapping, ("start", "end"))

    def test_user_layer_classification_supports_multiple_layers_and_auxiliary_roles(self):
        doc = self.new_doc()
        for layer in (
            "FRAME_A",
            "FRAME_B",
            "MISLEADING_WALER_NAME",
            "SUPPORT_SECOND",
            "DIAGONAL",
            "VERTICAL_AUX",
            "BEARER_AUX",
            "CORNER_AUX",
        ):
            doc.layers.add(layer)
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "FRAME_A"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "FRAME_B"})
        model.add_line(
            (250, 0),
            (250, 1000),
            dxfattribs={"layer": "MISLEADING_WALER_NAME"},
        )
        model.add_line((750, 0), (750, 1000), dxfattribs={"layer": "SUPPORT_SECOND"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "DIAGONAL"})
        model.add_line((100, 600), (900, 600), dxfattribs={"layer": "VERTICAL_AUX"})
        model.add_lwpolyline(
            [(100, 480), (900, 480), (900, 520), (100, 520)],
            close=True,
            dxfattribs={"layer": "BEARER_AUX"},
        )
        model.add_line((0, 0), (200, 200), dxfattribs={"layer": "CORNER_AUX"})
        self.counter += 1
        path = Path(self.temp_dir.name) / f"classified_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "FRAME_A": "waler",
                "FRAME_B": "waler",
                "MISLEADING_WALER_NAME": "strut",
                "SUPPORT_SECOND": "strut",
                "DIAGONAL": "brace",
                "VERTICAL_AUX": "column",
                "BEARER_AUX": "beam",
                "CORNER_AUX": "corner_brace",
            },
        )
        self.assertEqual(len(result.walers), 2)
        self.assertEqual(len(result.struts), 2)
        self.assertEqual(len(result.braces), 1)
        self.assertEqual(len(result.columns), 1)
        self.assertEqual(len(result.beams), 1)
        self.assertEqual(len(result.corner_braces), 1)
        self.assertEqual(
            result.selected_layers["waler"],
            ("FRAME_A", "FRAME_B"),
        )
        self.assertEqual(
            result.struts[0].source_layer,
            "MISLEADING_WALER_NAME",
        )
        self.assertTrue(result.can_import)
        rows = result.to_project_rows()
        self.assertEqual(len(rows["columns"]), 1)
        self.assertEqual(len(rows["beams"]), 1)
        self.assertEqual(len(rows["corner_braces"]), 1)
        first_strut_row = next(
            row for row in rows["struts"] if row["StartX"] == 250.0
        )
        self.assertEqual(first_strut_row["BeamPositions"], "500")
        self.assertEqual(first_strut_row["ColumnPositions"], "600")
        self.assertEqual(first_strut_row["AssociatedColumnIDs"], "C1")
        self.assertEqual(first_strut_row["AssociatedBeamIDs"], "BM1")
        self.assertEqual(result.struts[0].associated_columns, ("C1",))
        self.assertEqual(result.struts[0].associated_beams, ("BM1",))
        self.assertEqual(result.struts[1].associated_columns, ())
        self.assertEqual(result.struts[1].associated_beams, ("BM1",))
        self.assertEqual(result.columns[0].associated_strut_id, "S1")
        self.assertEqual(result.beams[0].associated_strut_id, "S1")
        self.assertEqual(rows["columns"][0]["AssociatedStrutID"], "S1")
        self.assertEqual(rows["beams"][0]["AssociatedStrutID"], "S1")
        self.assertEqual(result.beams[0].associated_strut_ids, ("S1", "S2"))
        self.assertEqual(len(result.beams[0].crossings), 2)
        self.assertEqual(len(result.component_associations), 3)
        self.assertEqual(
            {item["component_id"] for item in result.to_debug_dict()["component_associations"]},
            {"C1", "BM1"},
        )
        self.assertEqual(first_strut_row["FromBraceToWalerStartLen"], 250.0)
        corrected = select_engineering_line(result, "BM1", "line_2")
        corrected_strut_row = next(
            row
            for row in corrected.to_project_rows()["struts"]
            if row["StartX"] == 250.0
        )
        self.assertIn(corrected_strut_row["BeamPositions"], {"480", "520"})
        self.assertNotEqual(
            corrected_strut_row["BeamPositions"],
            first_strut_row["BeamPositions"],
        )

    def test_component_association_uses_nearest_valid_strut_and_rebuilds_after_edit(self):
        doc = self.new_doc()
        for layer in ("COLUMN", "BEAM"):
            doc.layers.add(layer)
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((200, 0), (200, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((800, 0), (800, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        model.add_line((700, 400), (820, 400), dxfattribs={"layer": "COLUMN"})
        model.add_lwpolyline(
            [(180, 680), (320, 680), (320, 720), (180, 720)],
            close=True,
            dxfattribs={"layer": "BEAM"},
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"association_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "COLUMN": "column",
                "BEAM": "beam",
            },
        )
        self.assertEqual(result.columns[0].associated_strut_id, "S2")
        self.assertEqual(result.beams[0].associated_strut_id, "S1")
        self.assertEqual(result.struts[0].associated_beams, ("BM1",))
        self.assertEqual(result.struts[1].associated_columns, ("C1",))

        localized = apply_coordinate_system(
            result,
            CoordinateSystem("local", 100.0, 200.0),
        )
        column_association = next(
            item
            for item in localized.component_associations
            if item.component_id == "C1"
        )
        self.assertEqual(column_association.world_projection_point, (800.0, 400.0))
        self.assertEqual(column_association.local_projection_point, (700.0, 200.0))
        localized_again = apply_coordinate_system(
            localized,
            CoordinateSystem("local", 100.0, 200.0),
        )
        self.assertEqual(
            next(
                item
                for item in localized_again.component_associations
                if item.component_id == "C1"
            ).local_projection_point,
            (700.0, 200.0),
        )

        pending, start_id, end_id = add_cad_candidate_points(
            result,
            "S1",
            (740, 0),
            (740, 1000),
        )
        corrected = apply_candidate_point_selection(
            pending,
            "S1",
            start_id,
            end_id,
            selection_source="cad_manual",
        )
        self.assertEqual(corrected.columns[0].associated_strut_id, "S1")
        self.assertEqual(corrected.struts[0].associated_columns, ("C1",))
        self.assertEqual(corrected.struts[1].associated_columns, ())

    def test_bent_mline_beam_keeps_path_and_creates_every_strut_crossing(self):
        doc = self.new_doc()
        doc.layers.add("BEAM")
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((250, 0), (250, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((750, 0), (750, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        beam_path = ((100, 200), (500, 200), (500, 800), (900, 800))
        model.add_mline(
            beam_path,
            dxfattribs={"layer": "BEAM", "justification": 1},
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"bent_mline_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "BEAM": "beam",
            },
        )

        self.assertEqual(len(result.beams), 1)
        beam = result.beams[0]
        self.assertEqual(beam.recognition_method, "mline_center_path")
        self.assertEqual(beam.world_path, beam_path)
        self.assertEqual(beam.associated_strut_ids, ("S1", "S2"))
        self.assertEqual(
            tuple(crossing.world_point for crossing in beam.crossings),
            ((250.0, 200.0), (750.0, 800.0)),
        )
        self.assertEqual(result.struts[0].beam_positions, (200.0,))
        self.assertEqual(result.struts[1].beam_positions, (800.0,))
        self.assertEqual(len(result.beam_crossings), 2)

        localized = apply_coordinate_system(
            result,
            CoordinateSystem("local", 100.0, 50.0),
        )
        self.assertEqual(localized.beams[0].world_path, beam_path)
        self.assertEqual(
            localized.beams[0].local_path,
            ((0.0, 150.0), (400.0, 150.0), (400.0, 750.0), (800.0, 750.0)),
        )
        self.assertEqual(
            tuple(crossing.local_point for crossing in localized.beam_crossings),
            ((150.0, 150.0), (650.0, 750.0)),
        )

    def test_top_justified_mline_beam_uses_section_center_not_outer_rail(self):
        doc = self.new_doc()
        doc.layers.add("BEAM")
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((250, 0), (250, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((750, 0), (750, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        model.add_mline(
            ((100, 400), (900, 400)),
            dxfattribs={
                "layer": "BEAM",
                "justification": 0,
                "scale_factor": 100.0,
            },
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"top_mline_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "BEAM": "beam",
            },
        )

        beam = result.beams[0]
        self.assertEqual(beam.world_path, ((100.0, 350.0), (900.0, 350.0)))
        self.assertEqual(beam.source_width, 100.0)
        self.assertEqual(
            tuple(crossing.world_point for crossing in beam.crossings),
            ((250.0, 350.0), (750.0, 350.0)),
        )
        self.assertEqual(result.struts[0].beam_positions, (350.0,))
        self.assertEqual(result.struts[1].beam_positions, (350.0,))

    def test_corner_brace_pair_uses_original_axis_member_intersections(self):
        doc = self.new_doc()
        doc.layers.add("CORNER")
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        block = doc.blocks.new("CORNER_PAIR")

        def add_brace(
            first_start,
            first_end,
            second_start,
            second_end,
            waler_contacts,
            strut_contacts,
        ):
            block.add_line(first_start, first_end)
            block.add_line(second_start, second_end)
            block.add_line(first_start, second_start)
            block.add_line(first_end, second_end)
            block.add_line(waler_contacts[0], first_start)
            block.add_line(waler_contacts[1], second_start)
            block.add_line(strut_contacts[0], first_end)
            block.add_line(strut_contacts[1], second_end)

        add_brace(
            (200, 200),
            (450, 450),
            (240, 160),
            (490, 410),
            ((100, 0), (300, 0)),
            ((500, 300), (500, 550)),
        )
        add_brace(
            (800, 200),
            (550, 450),
            (760, 160),
            (510, 410),
            ((900, 0), (700, 0)),
            ((500, 300), (500, 550)),
        )
        model.add_blockref(
            "CORNER_PAIR",
            (0, 0),
            dxfattribs={"layer": "CORNER"},
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"corner_pair_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "CORNER": "corner_brace",
            },
        )

        self.assertEqual(len(result.corner_braces), 2)
        self.assertEqual(
            {member.recognition_method for member in result.corner_braces},
            {"brace_centerline_intersections"},
        )
        self.assertEqual(
            {(member.world_start, member.world_end) for member in result.corner_braces},
            {
                ((40.0, 0.0), (500.0, 460.0)),
                ((500.0, 460.0), (960.0, 0.0)),
            },
        )
        strut = result.struts[0]
        self.assertEqual(strut.from_brace_to_waler_start_len, 460.0)
        self.assertEqual(strut.from_brace_to_waler_end_len, 460.0)
        self.assertFalse(
            any(
                message.code == "MULTIPLE_MODELS_FROM_ONE_SOURCE"
                for message in result.messages
            )
        )

    def test_h_section_column_uses_section_center_for_strut_association(self):
        doc = self.new_doc()
        doc.layers.add("COLUMN")
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((200, 0), (200, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((800, 0), (800, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        model.add_lwpolyline(
            [
                (740, 280),
                (860, 280),
                (860, 320),
                (820, 320),
                (820, 480),
                (860, 480),
                (860, 520),
                (740, 520),
                (740, 480),
                (780, 480),
                (780, 320),
                (740, 320),
            ],
            close=True,
            dxfattribs={"layer": "COLUMN"},
        )
        self.counter += 1
        path = Path(self.temp_dir.name) / f"h_section_column_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "COLUMN": "column",
            },
        )

        column = result.columns[0]
        self.assertEqual(column.recognition_method, "column_section_centroid")
        self.assertAlmostEqual(column.reference_point[0], 800.0)
        self.assertAlmostEqual(column.reference_point[1], 400.0)
        self.assertEqual(column.associated_strut_id, "S2")
        self.assertAlmostEqual(column.association_station, 400.0)
        self.assertEqual(result.struts[1].associated_columns, ("C1",))
        self.assertEqual(result.struts[1].column_positions, (400.0,))

        localized = apply_coordinate_system(
            result,
            CoordinateSystem("local", 100.0, 200.0),
        )
        self.assertEqual(localized.columns[0].world_reference_point, (800.0, 400.0))
        self.assertEqual(localized.columns[0].reference_point, (700.0, 200.0))
        self.assertEqual(localized.columns[0].local_reference_point, (700.0, 200.0))

    def test_component_outside_strut_effective_length_blocks_import(self):
        doc = self.new_doc()
        doc.layers.add("COLUMN")
        model = doc.modelspace()
        model.add_line((0, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        model.add_line((440, 1300), (560, 1300), dxfattribs={"layer": "COLUMN"})
        self.counter += 1
        path = Path(self.temp_dir.name) / f"unassociated_{self.counter}.dxf"
        doc.saveas(path)

        result = import_dxf(
            path,
            layer_roles={
                "WALER": "waler",
                "STRUT": "strut",
                "BRACE": "brace",
                "COLUMN": "column",
            },
        )
        self.assertFalse(result.can_import)
        self.assertEqual(result.columns[0].associated_strut_id, "")
        self.assertTrue(
            any(message.code == "COLUMN_NOT_ASSOCIATED" for message in result.messages)
        )

    def test_column_association_allows_section_aware_500_mm_offset(self):
        strut = Strut(
            id="S1",
            start=(0.0, 0.0),
            end=(0.0, 1000.0),
            source_layer="STRUT",
            source_handles=("S",),
            source_entity_types=("LINE",),
            recognition_method="existing_centerline",
            centerline_computed=False,
            source_width=350.0,
            from_waler="W1",
            to_waler="W2",
            confidence=1.0,
        )
        column = Column(
            id="C1",
            start=(290.0, 500.0),
            end=(710.0, 500.0),
            source_layer="COLUMN",
            source_handles=("C",),
            source_entity_types=("INSERT",),
            recognition_method="column_section_centroid",
            centerline_computed=True,
            source_width=420.0,
            confidence=1.0,
            reference_point=(500.0, 500.0),
            world_reference_point=(500.0, 500.0),
        )

        associated_struts, columns, _beams, _records, messages = (
            associate_components_to_struts((strut,), (column,), ())
        )

        self.assertEqual(columns[0].associated_strut_id, "S1")
        self.assertAlmostEqual(columns[0].association_distance, 500.0)
        self.assertEqual(associated_struts[0].associated_columns, ("C1",))
        self.assertEqual(associated_struts[0].column_positions, (500.0,))
        self.assertFalse(
            any(message.code == "COLUMN_NOT_ASSOCIATED" for message in messages)
        )

    def test_rectangle_strut_with_centerline_prefers_existing_line(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_vertical_walers(model)
        block = doc.blocks.new(name="STRUT_WITH_CENTER")
        block.add_lwpolyline([(0, -20), (1000, -20), (1000, 20), (0, 20)], close=True)
        block.add_line((0, 0), (1000, 0))
        block.add_text("S")
        insert = model.add_blockref("STRUT_WITH_CENTER", (0, 500), dxfattribs={"layer": "STRUT"})
        model.add_line((0, 100), (1000, 900), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        self.assertEqual(len(result.struts), 1)
        member = result.struts[0]
        self.assertEqual(member.recognition_method, "existing_centerline")
        self.assertFalse(member.centerline_computed)
        self.assertEqual(member.source_handles, (insert.dxf.handle,))
        self.assertIn("INSERT", member.source_entity_types)
        self.assertIn("LWPOLYLINE", member.source_entity_types)
        self.assertNotIn("TEXT", member.source_entity_types)
        self.assertEqual((member.from_waler, member.to_waler), ("W1", "W2"))

    def test_rectangle_only_strut_computes_one_centerline(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_vertical_walers(model)
        model.add_lwpolyline(
            [(0, 480), (1000, 480), (1000, 520), (0, 520)],
            close=True,
            dxfattribs={"layer": "STRUT"},
        )
        model.add_line((0, 100), (1000, 900), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        self.assertEqual(len(result.struts), 1)
        self.assertEqual(result.struts[0].recognition_method, "closed_outline_axis")
        self.assertTrue(result.struts[0].centerline_computed)

    def test_diagonal_rectangle_brace_computes_one_arbitrary_angle_axis(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_vertical_walers(model)
        model.add_line((0, 500), (1000, 500), dxfattribs={"layer": "STRUT"})
        model.add_lwpolyline(
            self.outline_around((0, 0), (1000, 1000), 20),
            close=True,
            dxfattribs={"layer": "BRACE"},
        )
        result, _path = self.convert(doc)
        self.assertEqual(len(result.braces), 1)
        brace = result.braces[0]
        self.assertTrue(brace.centerline_computed)
        self.assertAlmostEqual(abs((brace.end[1] - brace.start[1]) / (brace.end[0] - brace.start[0])), 1.0, places=3)
        self.assertTrue(result.can_import)

    def test_brace_outline_and_center_line_are_deduplicated(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_vertical_walers(model)
        model.add_line((0, 500), (1000, 500), dxfattribs={"layer": "STRUT"})
        line = model.add_line((0, 0), (1000, 1000), dxfattribs={"layer": "BRACE"})
        outline = model.add_lwpolyline(
            self.outline_around((0, 0), (1000, 1000), 20),
            close=True,
            dxfattribs={"layer": "BRACE"},
        )
        result, _path = self.convert(doc)
        self.assertEqual(len(result.braces), 1)
        self.assertEqual(result.braces[0].recognition_method, "existing_centerline")
        self.assertEqual(set(result.braces[0].source_handles), {line.dxf.handle, outline.dxf.handle})
        self.assertIn("DUPLICATED_COMPONENT", {message.code for message in result.messages})
        duplicate_problem = next(
            item for item in build_problem_records(result)
            if item.code == "DUPLICATED_COMPONENT"
        )
        self.assertEqual(duplicate_problem.component, "B1")
        self.assertIn(
            "重複幾何已自動合併",
            " ".join(item.text for item in build_validation_overview(result)),
        )

    def test_rotated_and_scaled_insert_uses_world_coordinates(self):
        doc = self.new_doc()
        model = doc.modelspace()
        angle = math.radians(30)
        start = (100.0, 200.0)
        end = (100 + 1000 * math.cos(angle), 200 + 1000 * math.sin(angle))
        normal = (-math.sin(angle), math.cos(angle))
        for point in (start, end):
            model.add_line(
                (point[0] - normal[0] * 200, point[1] - normal[1] * 200),
                (point[0] + normal[0] * 200, point[1] + normal[1] * 200),
                dxfattribs={"layer": "WALER"},
            )
        block = doc.blocks.new(name="ROTATED_STRUT")
        block.add_lwpolyline([(0, -5), (500, -5), (500, 5), (0, 5)], close=True)
        block.add_line((0, 0), (500, 0))
        insert = model.add_blockref(
            "ROTATED_STRUT",
            start,
            dxfattribs={"layer": "STRUT", "rotation": 30, "xscale": 2, "yscale": 3},
        )
        model.add_line(start, end, dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        member = result.struts[0]
        self.assertAlmostEqual(_distance(member.start, start), 0, places=5)
        self.assertAlmostEqual(_distance(member.end, end), 0, places=5)
        instance = member.block_instances[0]
        self.assertEqual(instance.block_name, "ROTATED_STRUT")
        self.assertEqual(instance.handle, insert.dxf.handle)
        self.assertEqual(instance.rotation, 30)
        self.assertEqual(instance.xscale, 2)
        self.assertEqual(instance.yscale, 3)

    def test_near_waler_endpoint_is_connected_and_snapped(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        model.add_line((500, 100), (500, 900), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 100), (900, 900), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        self.assertEqual((result.struts[0].from_waler, result.struts[0].to_waler), ("W1", "W2"))
        self.assertEqual(result.struts[0].start[1], 0)
        self.assertEqual(result.struts[0].end[1], 1000)

    def test_unconnected_endpoint_blocks_solver_export(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        model.add_line((500, 0), (500, 500), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        self.assertFalse(result.can_import)
        self.assertIn("STRUT_ONE_END_NOT_CONNECTED", {message.code for message in result.messages})
        connection_problem = next(
            item for item in build_problem_records(result)
            if item.code == "STRUT_ONE_END_NOT_CONNECTED"
        )
        self.assertEqual(connection_problem.component, "S1")
        self.assertEqual(connection_problem.severity, "error")
        with self.assertRaises(DXFImportError):
            result.to_project_rows()

    def test_multiple_near_walers_marks_ambiguous_connection(self):
        doc = self.new_doc()
        model = doc.modelspace()
        model.add_line((-500, 0), (1000, 0), dxfattribs={"layer": "WALER"})
        model.add_line((0, -500), (0, 500), dxfattribs={"layer": "WALER"})
        model.add_line((-500, 1000), (1000, 1000), dxfattribs={"layer": "WALER"})
        model.add_line((5, 5), (500, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(doc)
        self.assertIn("AMBIGUOUS_WALER_CONNECTION", {message.code for message in result.messages})
        self.assertTrue(result.struts[0].from_waler)

    def test_summary_precedes_full_debug_and_append_ids_are_remapped(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        result, _path = self.convert(doc)
        debug = result.to_debug_dict()
        self.assertEqual(next(iter(debug)), "summary")
        self.assertTrue(debug["summary"]["can_import"])
        json.dumps(debug)
        rows = result.to_project_rows(
            {
                "walers": [{"WalerID": "W1"}],
                "struts": [{"StrutID": "S1"}],
                "braces": [{"BraceID": "B1"}],
            }
        )
        self.assertEqual([row["WalerID"] for row in rows["walers"]], ["W2", "W3"])
        self.assertEqual(rows["struts"][0]["FromWaler"], "W2")

    def test_local_coordinate_system_preserves_world_and_feeds_local_rows(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        self.add_default_strut_and_brace(model)
        world_result, _path = self.convert(doc)
        original_geometry = world_result.source_geometry
        local_result = apply_coordinate_system(
            world_result,
            CoordinateSystem("local", 100.0, -200.0, "user_input"),
        )
        member = local_result.struts[0]
        self.assertEqual(member.world_start, (500.0, 0.0))
        self.assertEqual(member.world_end, (500.0, 1000.0))
        self.assertEqual(member.local_start, (400.0, 200.0))
        self.assertEqual(member.local_end, (400.0, 1200.0))
        self.assertEqual(member.start, member.local_start)
        self.assertEqual(member.end, member.local_end)
        self.assertEqual(world_result.struts[0].start, (500.0, 0.0))
        self.assertEqual(local_result.source_geometry, original_geometry)
        rows = local_result.to_project_rows()
        self.assertEqual(rows["struts"][0]["StartX"], 400.0)
        self.assertEqual(rows["struts"][0]["StartY"], 200.0)
        self.assertEqual(
            local_result.to_debug_dict()["coordinate_system"],
            {
                "mode": "local",
                "origin_x": 100.0,
                "origin_y": -200.0,
                "source": "user_input",
            },
        )

    def test_coordinate_origin_validation_messages(self):
        with self.assertRaisesRegex(DXFImportError, "請輸入原點座標"):
            parse_coordinate_origin("", "20")
        with self.assertRaisesRegex(DXFImportError, "原點座標格式錯誤"):
            parse_coordinate_origin("not-a-number", "20")
        with self.assertRaisesRegex(DXFImportError, "原點座標格式錯誤"):
            parse_coordinate_origin("NaN", "20")
        self.assertEqual(parse_coordinate_origin("338238.287", "-725295.570"), (338238.287, -725295.57))

    def test_rectangle_centerline_supports_rotation(self):
        centerline = rectangle_centerline([(0, 0), (10, 10), (8, 12), (-2, 2)])
        self.assertIsNotNone(centerline)
        start, end = centerline
        self.assertAlmostEqual(start[0], -1)
        self.assertAlmostEqual(start[1], 1)
        self.assertAlmostEqual(end[0], 9)
        self.assertAlmostEqual(end[1], 11)

    def test_component_too_short_uses_central_tolerance_configuration(self):
        doc = self.new_doc()
        model = doc.modelspace()
        self.add_horizontal_walers(model)
        model.add_line((500, 0), (500, 1000), dxfattribs={"layer": "STRUT"})
        model.add_line((100, 0), (900, 1000), dxfattribs={"layer": "BRACE"})
        result, _path = self.convert(
            doc,
            tolerances=GeometryTolerances(minimum_component_length_mm=2000),
        )
        self.assertIn("COMPONENT_TOO_SHORT", {message.code for message in result.messages})
        self.assertFalse(result.can_import)


class _IdleQueue:
    def __init__(self):
        self.callbacks = []

    def after_idle(self, callback):
        self.callbacks.append(callback)
        return len(self.callbacks)

    def flush(self):
        while self.callbacks:
            callbacks, self.callbacks = self.callbacks, []
            for callback in callbacks:
                callback()


class _FakeTree:
    def __init__(self):
        self.rows = {}
        self._selection = ()
        self.focused = ""

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *iids):
        for iid in iids:
            self.rows.pop(iid, None)
        if any(iid in self._selection for iid in iids):
            self._selection = ()

    def insert(self, _parent, _position, *, iid, values):
        self.rows[iid] = {"values": tuple(values), "tags": ()}

    def exists(self, iid):
        return iid in self.rows

    def selection(self):
        return self._selection

    def selection_set(self, iid):
        self._selection = (iid,)

    def focus(self, iid):
        self.focused = iid

    def see(self, _iid):
        return None

    def item(self, iid, **options):
        self.rows[iid].update(options)

    def tag_configure(self, _tag, **_options):
        return None


class _FakeCanvas:
    def __init__(self):
        self.next_id = 1
        self.items = {}

    def _create(self, kind, coordinates, options):
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {
            "kind": kind,
            "coordinates": tuple(coordinates),
            "tags": tuple(options.get("tags", ())),
            **options,
        }
        return item_id

    def create_line(self, *coordinates, **options):
        return self._create("line", coordinates, options)

    def create_oval(self, *coordinates, **options):
        return self._create("oval", coordinates, options)

    def create_text(self, *coordinates, **options):
        return self._create("text", coordinates, options)

    def create_rectangle(self, *coordinates, **options):
        return self._create("rectangle", coordinates, options)

    def delete(self, target):
        if target == "all":
            self.items.clear()
            return
        for item_id in tuple(self.items):
            if target in self.items[item_id]["tags"]:
                del self.items[item_id]

    def find_all(self):
        return tuple(self.items)


class DXFSelectionArchitectureTests(unittest.TestCase):
    @staticmethod
    def candidate(identifier, x, y, recommended_for=()):
        return CandidatePoint(
            identifier,
            (float(x), float(y)),
            (float(x), float(y)),
            "test_point",
            identifier,
            recommended_for=tuple(recommended_for),
            point_types=("test_point",),
        )

    def make_controller(self):
        points = (
            self.candidate("P01", 0, 0, ("start",)),
            self.candidate("P02", 10, 0, ("end",)),
            self.candidate("P03", 2, 0),
        )
        member = SimpleNamespace(
            id="S1",
            candidate_points=points,
            selected_start_point_id="P01",
            selected_end_point_id="P02",
            recommended_start_point_id="P01",
            recommended_end_point_id="P02",
            selection_source="auto",
            start=(0.0, 0.0),
            end=(10.0, 0.0),
        )
        store = CandidatePointStore(0.1)
        store.register_component(member.id, points)
        state = SelectionState()
        dirty = []
        controller = SelectionController(
            state,
            store,
            lambda identifier: member if identifier == member.id else None,
            dirty.append,
        )
        return member, store, state, dirty, controller

    def test_selection_state_is_idempotent_and_records_source(self):
        _member, _store, state, dirty, controller = self.make_controller()
        self.assertTrue(controller.select_component("S1", "canvas"))
        revision = state.revision
        self.assertEqual(state.selection_source, "canvas")
        self.assertFalse(controller.select_component("S1", "component_tree"))
        self.assertEqual(state.revision, revision)
        dirty.clear()
        self.assertTrue(controller.select_candidate_point("P03", "canvas"))
        self.assertEqual(state.selected_candidate_point_id, "P03")
        self.assertEqual(state.pending_start_point_id, "P01")
        self.assertEqual(state.pending_end_point_id, "P02")
        self.assertFalse(dirty[-1] & RenderDirty.FULL_SCENE)
        self.assertFalse(dirty[-1] & RenderDirty.COMPONENT_LAYER)
        self.assertFalse(dirty[-1] & RenderDirty.CANDIDATE_LAYER)
        revision = state.revision
        self.assertFalse(controller.select_candidate_point("P03", "candidate_tree"))
        self.assertEqual(state.revision, revision)

    def test_hover_pending_and_formal_selection_are_separate(self):
        member, _store, state, _dirty, controller = self.make_controller()
        controller.select_component("S1", "programmatic")
        controller.set_hovered_candidate("P03")
        self.assertEqual(state.hovered_candidate_point_id, "P03")
        self.assertEqual(state.selected_start_point_id, "P01")
        self.assertEqual(state.pending_start_point_id, "P01")
        self.assertEqual(member.start, (0.0, 0.0))
        controller.begin_pick_start()
        controller.select_candidate_point("P03", "candidate_tree")
        self.assertEqual(state.pending_start_point_id, "P03")
        self.assertEqual(state.selected_start_point_id, "P01")
        self.assertEqual(member.start, (0.0, 0.0))
        controller.cancel_pending()
        self.assertEqual(state.pending_start_point_id, "P01")
        controller.swap_pending_points()
        self.assertEqual(
            (state.pending_start_point_id, state.pending_end_point_id),
            ("P02", "P01"),
        )
        controller.restore_recommended_points()
        self.assertEqual(
            (state.pending_start_point_id, state.pending_end_point_id),
            ("P01", "P02"),
        )
        self.assertEqual(
            (state.selected_start_point_id, state.selected_end_point_id),
            ("P01", "P02"),
        )

    def test_candidate_tree_selection_is_incremental_and_generation_guarded(self):
        _member, store, state, _dirty, controller = self.make_controller()
        controller.select_component("S1", "programmatic")
        queue = _IdleQueue()
        tree = _FakeTree()
        adapter = CandidateTreeAdapter(tree, queue.after_idle)
        adapter.rebuild(
            "S1",
            store.component_points("S1"),
            lambda point: (point.id, point.label),
        )
        self.assertEqual(adapter.rebuild_count, 1)
        self.assertTrue(adapter.sync_selection("P03"))
        self.assertTrue(adapter.syncing)
        self.assertEqual(adapter.point_id_for_iid(tree.selection()[0]), "P03")
        queue.flush()
        self.assertFalse(adapter.syncing)
        adapter.update_row("P03", ("P03", "updated"))
        adapter.set_hover("P03")
        adapter.set_hover("")
        self.assertEqual(adapter.rebuild_count, 1)
        self.assertFalse(adapter.sync_selection("P03"))

    def test_render_scheduler_coalesces_and_preserves_reentrant_updates(self):
        queue = _IdleQueue()
        rendered = []
        scheduler = None

        def render(dirty):
            rendered.append(dirty)
            if len(rendered) == 1:
                scheduler.request(RenderDirty.HOVER)

        scheduler = RenderScheduler(queue.after_idle, render)
        scheduler.request(RenderDirty.CANDIDATE_SELECTION)
        scheduler.request(RenderDirty.TEMP_LINE)
        self.assertEqual(len(queue.callbacks), 1)
        queue.flush()
        self.assertEqual(len(rendered), 2)
        self.assertTrue(rendered[0] & RenderDirty.CANDIDATE_SELECTION)
        self.assertTrue(rendered[0] & RenderDirty.TEMP_LINE)
        self.assertEqual(rendered[1], RenderDirty.HOVER)

    def test_preview_layer_delete_preserves_unrelated_item_ids(self):
        canvas = _FakeCanvas()
        scene = PreviewScene()
        renderer = PreviewRenderer(canvas, scene)
        source_id = renderer.create_line(
            "source_geometry", 0, 0, 10, 0, source_handle="H1"
        )
        member_id = renderer.create_line(
            "engineering_members", 0, 0, 0, 10, component_id="S1"
        )
        candidate_id = renderer.create_oval(
            "candidate_overlay",
            0,
            0,
            5,
            5,
            candidate_point_id="P01",
        )
        renderer.delete_layer("candidate_overlay")
        self.assertIn(source_id, canvas.items)
        self.assertIn(member_id, canvas.items)
        self.assertNotIn(candidate_id, canvas.items)
        self.assertEqual(scene.source_handle_items["H1"], [source_id])
        self.assertEqual(scene.component_items["S1"], [member_id])
        self.assertNotIn("P01", scene.candidate_point_items)


def _distance(first, second):
    return math.hypot(first[0] - second[0], first[1] - second[1])


if __name__ == "__main__":
    unittest.main()
    apply_coordinate_system,
