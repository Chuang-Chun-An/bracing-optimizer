from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from bracing_optimizer.infrastructure.dxf_result_export import (
    APP_ID,
    CLEAN_DXF_ACAD_VERSION,
    JACK_BLOCK_NAME,
    PROJECT_BRACE_LAYER,
    PROJECT_STRUT_LAYER,
    PROJECT_WALER_LAYER,
    RESULT_SUPPORT_LAYER,
    RESULT_WALER_LAYER,
    WARNING_ANCHOR_TOLERANCE_MM,
    WARNING_FONT_FAMILY,
    WARNING_FONT_FILE,
    WARNING_INVALID_RESULT_LAYER,
    WARNING_TEXT_OFFSET_MM,
    WARNING_TEXT_STYLE,
    DXFExportMode,
    DXFResultExportError,
    ExportCoordinateSystem,
    ExportPiece,
    MemberExportPlan,
    build_project_geometry_segments,
    build_project_member_bindings,
    export_coordinate_system_from_import_state,
    export_results_to_dxf,
    resolve_dxf_export_context,
)
from main import SupportInputApp


def clean_import_state(*, source_path: str = "") -> dict:
    ox, oy = 100_000.0, -200_000.0
    return {
        "source_path": source_path,
        "coordinate_system": {
            "mode": "local",
            "origin_x": ox,
            "origin_y": oy,
        },
        "selected_layers": {
            "waler": "WALER_SOURCE",
            "strut": "STRUT_SOURCE",
            "brace": "BRACE_SOURCE",
            "corner_brace": "CORNER_SOURCE",
            "column": "COLUMN_SOURCE",
            "beam": "BEAM_SOURCE",
            "auxiliary": ["AUX_SOURCE"],
        },
        "validation_messages": [],
        "source_geometry": [
            {
                "role": "waler",
                "source_handle": "OLD-W",
                "points": [[ox, oy], [ox + 3000, oy]],
                "closed": False,
                "source_layer": "WALER_SOURCE",
                "source_entity_type": "LINE",
            },
            {
                "role": "strut",
                "source_handle": "OLD-S",
                "points": [[ox + 5000, oy], [ox + 5000, oy + 2600]],
                "closed": False,
                "source_layer": "STRUT_SOURCE",
                "source_entity_type": "LINE",
            },
            {
                "role": "brace",
                "source_handle": "OLD-B",
                "points": [[ox, oy], [ox + 1000, oy + 1000]],
                "closed": False,
                "source_layer": "BRACE_SOURCE",
                "source_entity_type": "LINE",
            },
            {
                "role": "corner_brace",
                "source_handle": "OLD-CB",
                "points": [[ox + 2000, oy], [ox + 2500, oy + 500]],
                "closed": False,
                "source_layer": "CORNER_SOURCE",
                "source_entity_type": "LINE",
            },
            {
                "role": "column",
                "source_handle": "OLD-C",
                "points": [
                    [ox + 3000, oy + 1000],
                    [ox + 3200, oy + 1000],
                    [ox + 3200, oy + 1200],
                    [ox + 3000, oy + 1200],
                ],
                "closed": True,
                "source_layer": "COLUMN_SOURCE",
                "source_entity_type": "LWPOLYLINE",
            },
            {
                "role": "beam",
                "source_handle": "OLD-BM",
                "points": [
                    [ox + 1000, oy + 1500],
                    [ox + 2000, oy + 1500],
                    [ox + 2500, oy + 1800],
                ],
                "closed": False,
                "source_layer": "BEAM_SOURCE",
                "source_entity_type": "LWPOLYLINE",
            },
            {
                "role": "auxiliary",
                "source_handle": "OLD-A",
                "points": [[ox - 500, oy - 500], [ox + 6000, oy - 500]],
                "closed": False,
                "source_layer": "AUX_SOURCE",
                "source_entity_type": "LINE",
            },
        ],
        "converted": {
            "walers": [
                {
                    "id": "W1",
                    "source_handles": ["OLD-W"],
                    "source_layer": "WALER_SOURCE",
                    "start": [0, 0],
                    "end": [3000, 0],
                    "local_start": [0, 0],
                    "local_end": [3000, 0],
                    "world_start": [ox, oy],
                    "world_end": [ox + 3000, oy],
                }
            ],
            "struts": [
                {
                    "id": "S1",
                    "source_handles": ["OLD-S"],
                    "source_layer": "STRUT_SOURCE",
                    "start": [5000, 0],
                    "end": [5000, 2600],
                    "local_start": [5000, 0],
                    "local_end": [5000, 2600],
                    "world_start": [ox + 5000, oy],
                    "world_end": [ox + 5000, oy + 2600],
                }
            ],
            "braces": [
                {
                    "id": "B1",
                    "source_layer": "BRACE_SOURCE",
                    "start": [0, 0],
                    "end": [1000, 1000],
                    "world_start": [ox, oy],
                    "world_end": [ox + 1000, oy + 1000],
                }
            ],
            "corner_braces": [
                {
                    "id": "CB1",
                    "source_layer": "CORNER_SOURCE",
                    "start": [2000, 0],
                    "end": [2500, 500],
                    "world_start": [ox + 2000, oy],
                    "world_end": [ox + 2500, oy + 500],
                }
            ],
            "columns": [
                {
                    "id": "C1",
                    "source_layer": "COLUMN_SOURCE",
                    "start": [3100, 1000],
                    "end": [3100, 1200],
                    "world_start": [ox + 3100, oy + 1000],
                    "world_end": [ox + 3100, oy + 1200],
                }
            ],
            "beams": [
                {
                    "id": "BM1",
                    "source_layer": "BEAM_SOURCE",
                    "start": [1000, 1500],
                    "end": [2500, 1800],
                    "world_path": [
                        [ox + 1000, oy + 1500],
                        [ox + 2000, oy + 1500],
                        [ox + 2500, oy + 1800],
                    ],
                }
            ],
        },
    }


def basic_project_rows():
    return (
        [{"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0}],
        [
            {
                "StrutID": "S1",
                "StartX": 5000,
                "StartY": 0,
                "EndX": 5000,
                "EndY": 2600,
            }
        ],
        [{"BraceID": "B1", "StartX": 0, "StartY": 0, "EndX": 1000, "EndY": 1000}],
    )


def basic_coordinate() -> ExportCoordinateSystem:
    return ExportCoordinateSystem("local", 100_000, -200_000)


def basic_bindings():
    walers, struts, _braces = basic_project_rows()
    return build_project_member_bindings(walers, struts, basic_coordinate())


def basic_plans() -> tuple[MemberExportPlan, ...]:
    return (
        MemberExportPlan(
            "W1",
            "waler",
            (
                ExportPiece("steel", 1000),
                ExportPiece("steel", 1850),
                ExportPiece("shim", 100),
            ),
            gap=50,
            result_id="W1-plan-1",
        ),
        MemberExportPlan(
            "S1",
            "strut",
            (
                ExportPiece("steel", 1000),
                ExportPiece("jack", 600),
                ExportPiece("shim", 100),
                ExportPiece("steel", 800),
            ),
            gap=100,
            result_id="zone-plan-1",
        ),
    )


def export_basic(output_path, plans=None, state=None):
    walers, struts, braces = basic_project_rows()
    return export_results_to_dxf(
        output_path,
        basic_plans() if plans is None else plans,
        walers,
        struts,
        braces,
        basic_coordinate(),
        export_mode=DXFExportMode.SOURCE_BACKED,
        background_state=state or clean_import_state(),
    )


class DXFResultExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_clean_r2018_world_coordinate_result_dxf(self):
        output_path = self.temp_path / "中文 空格 clean result.dxf"

        report = export_basic(output_path)

        self.assertTrue(output_path.is_file())
        self.assertEqual(CLEAN_DXF_ACAD_VERSION, ezdxf.readfile(output_path).dxfversion)
        self.assertEqual("mm", report.coordinate_units)
        self.assertEqual("local", report.coordinate_mode)
        self.assertEqual(DXFExportMode.SOURCE_BACKED, report.export_mode)
        self.assertIn("使用原始世界座標建立", report.merge_guidance)
        self.assertEqual(8, report.dimension_count)
        self.assertEqual(1, report.jack_count)
        self.assertEqual(0, report.final_audit.error_count)
        self.assertEqual(0, report.final_audit.fix_count)
        self.assertEqual(report.dimension_count, report.actual_dimension_count)
        self.assertEqual(report.jack_count, report.actual_jack_count)

        exported = ezdxf.readfile(output_path)
        self.assertEqual(4, exported.header["$INSUNITS"])
        dimensions = list(exported.modelspace().query("DIMENSION"))
        jacks = [
            entity
            for entity in exported.modelspace().query("INSERT")
            if entity.dxf.name == JACK_BLOCK_NAME
        ]
        self.assertEqual(8, len(dimensions))
        self.assertEqual(1, len(jacks))
        self.assertEqual(
            4,
            sum(entity.dxf.layer == RESULT_WALER_LAYER for entity in dimensions),
        )
        self.assertEqual(
            4,
            sum(entity.dxf.layer == RESULT_SUPPORT_LAYER for entity in dimensions),
        )
        self.assertEqual(RESULT_SUPPORT_LAYER, jacks[0].dxf.layer)
        self.assertAlmostEqual(90.0, jacks[0].dxf.rotation, places=6)
        self.assertTrue(all(entity.has_xdata(APP_ID) for entity in dimensions))
        self.assertTrue(all(entity.dxf.layer == "0" for entity in exported.blocks[JACK_BLOCK_NAME]))

    def test_exports_16450_waler_with_one_tail_adjustment_and_gap(self):
        output_path = self.temp_path / "waler-16450.dxf"
        plan = MemberExportPlan(
            "W1",
            "waler",
            (
                ExportPiece("steel", 8000),
                ExportPiece("steel", 8000),
                ExportPiece("shim", 300),
            ),
            gap=150,
            result_id="W1-plan",
        )

        report = export_results_to_dxf(
            output_path,
            (plan,),
            [{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 16450,
                "EndY": 0,
            }],
            [],
            [],
            ExportCoordinateSystem("world"),
            export_mode=DXFExportMode.RESULT_ONLY,
        )

        self.assertEqual(report.dimension_count, 4)
        document = ezdxf.readfile(output_path)
        displayed = []
        for dimension in document.modelspace().query("DIMENSION"):
            values = [tag.value for tag in dimension.get_xdata(APP_ID)]
            block = document.blocks.get(dimension.dxf.geometry)
            text = [
                str(entity.dxf.get("text", ""))
                for entity in block
                if entity.dxftype() in {"MTEXT", "TEXT"}
            ]
            displayed.append((int(values[5]), text[0], dimension.get_measurement()))
        self.assertEqual(
            displayed,
            [
                (1, "8000", 8000.0),
                (2, "8000", 8000.0),
                (3, "調整塊 300", 300.0),
                (4, "餘量 150", 150.0),
            ],
        )

    def test_reconstructs_every_required_background_role_and_deduplicates_lines(self):
        output_path = self.temp_path / "background.dxf"
        report = export_basic(output_path)

        self.assertEqual(
            {"corner_brace", "column", "beam", "auxiliary"},
            {role for role, _count in report.background_counts},
        )
        # Formal Waler/Strut/Brace source lines are intentionally excluded.
        self.assertEqual(9, report.background_segment_count)
        self.assertEqual(
            {"waler", "strut", "brace"},
            {role for role, _count in report.project_counts},
        )
        exported = ezdxf.readfile(output_path)
        background_lines = [
            entity
            for entity in exported.modelspace().query("LINE")
            if entity.has_xdata(APP_ID)
            and tuple(tag.value for tag in entity.get_xdata(APP_ID))[:2]
            == ("clean_dxf_export_v1", "background")
        ]
        self.assertEqual(report.background_segment_count, len(background_lines))

    def test_local_render_keeps_y1a_s1_values_and_transforms_geometry_to_world(self):
        start = (341788.2870494365, -724845.5055624783)
        end = (341788.28704949556, -703545.508980495)
        state = {
            "coordinate_system": {"mode": "world", "origin_x": 0, "origin_y": 0},
            "validation_messages": [],
            "source_geometry": [
                {
                    "role": "strut",
                    "source_handle": "Y1A-S1",
                    "points": [start, end],
                    "closed": False,
                    "source_layer": "STRUT_SOURCE",
                    "source_entity_type": "LINE",
                }
            ],
            "converted": {
                "walers": [],
                "struts": [
                    {
                        "id": "S1",
                        "source_layer": "STRUT_SOURCE",
                        "start": start,
                        "end": end,
                        "world_start": start,
                        "world_end": end,
                    }
                ],
                "braces": [],
                "corner_braces": [],
                "columns": [],
                "beams": [],
            },
        }
        struts = [
            {
                "StrutID": "S1",
                "StartX": start[0],
                "StartY": start[1],
                "EndX": end[0],
                "EndY": end[1],
            }
        ]
        plan = MemberExportPlan(
            "S1",
            "strut",
            (
                ExportPiece("steel", 9500),
                ExportPiece("jack", 600),
                ExportPiece("shim", 100),
                ExportPiece("steel", 4000),
                ExportPiece("steel", 7000),
            ),
            gap=100,
            result_id="Y1A-S1-local-render",
        )
        output_path = self.temp_path / "Y1A-S1-local-render.dxf"

        export_results_to_dxf(
            output_path,
            (plan,),
            [],
            struts,
            [],
            ExportCoordinateSystem("world"),
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_state=state,
        )

        document = ezdxf.readfile(output_path)
        displayed = []
        for dimension in document.modelspace().query("DIMENSION"):
            values = [tag.value for tag in dimension.get_xdata(APP_ID)]
            self.assertEqual("S1", values[2])
            block = document.blocks.get(dimension.dxf.geometry)
            text = [
                str(entity.dxf.get("text", ""))
                for entity in block
                if entity.dxftype() in {"MTEXT", "TEXT"}
            ]
            displayed.append((int(values[5]), text[0], dimension.get_measurement()))
            # Anonymous-block geometry has already been translated from member
            # local coordinates into the original Y1A world-coordinate area.
            for entity in block:
                if entity.dxftype() == "LINE":
                    self.assertGreater(entity.dxf.start.x, 300_000)
                    self.assertLess(entity.dxf.start.y, -600_000)
                elif entity.dxftype() == "MTEXT":
                    self.assertGreater(entity.dxf.insert.x, 300_000)
                    self.assertLess(entity.dxf.insert.y, -600_000)
                elif entity.dxftype() == "INSERT":
                    self.assertGreater(entity.dxf.insert.x, 300_000)
                    self.assertLess(entity.dxf.insert.y, -600_000)
                elif entity.dxftype() == "SOLID":
                    self.assertGreater(entity.dxf.vtx0.x, 300_000)
                    self.assertLess(entity.dxf.vtx0.y, -600_000)

        self.assertEqual(
            [
                (1, "9500", 9500.0),
                (3, "調整塊 100", 100.0),
                (4, "4000", 4000.0),
                (5, "7000", 7000.0),
                (6, "餘量 100", 100.0),
            ],
            displayed,
        )

    def test_local_render_preserves_diagonal_dimension_values_in_world_coordinates(self):
        start = (338238.287, -724845.506)
        length = 3000.0
        end = (
            start[0] + length / math.sqrt(2.0),
            start[1] + length / math.sqrt(2.0),
        )
        state = {
            "coordinate_system": {"mode": "world", "origin_x": 0, "origin_y": 0},
            "validation_messages": [],
            "source_geometry": [
                {
                    "role": "strut",
                    "source_handle": "DIAGONAL-S1",
                    "points": [start, end],
                    "closed": False,
                    "source_layer": "STRUT_SOURCE",
                    "source_entity_type": "LINE",
                }
            ],
            "converted": {
                "walers": [],
                "struts": [
                    {
                        "id": "S1",
                        "source_layer": "STRUT_SOURCE",
                        "start": start,
                        "end": end,
                        "world_start": start,
                        "world_end": end,
                    }
                ],
                "braces": [],
                "corner_braces": [],
                "columns": [],
                "beams": [],
            },
        }
        struts = [
            {
                "StrutID": "S1",
                "StartX": start[0],
                "StartY": start[1],
                "EndX": end[0],
                "EndY": end[1],
            }
        ]
        plan = MemberExportPlan(
            "S1",
            "strut",
            (ExportPiece("steel", 1400), ExportPiece("jack", 600), ExportPiece("steel", 1000)),
            result_id="diagonal",
        )
        output_path = self.temp_path / "diagonal-local-render.dxf"

        report = export_results_to_dxf(
            output_path,
            (plan,),
            [],
            struts,
            [],
            ExportCoordinateSystem("world"),
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_state=state,
        )

        document = ezdxf.readfile(output_path)
        self.assertEqual(2, report.dimension_count)
        self.assertEqual(1, report.jack_count)
        dimensions = list(document.modelspace().query("DIMENSION"))
        for expected, item in zip((1400.0, 1000.0), dimensions):
            self.assertAlmostEqual(expected, item.get_measurement(), places=6)
        self.assertTrue(
            all(tuple(item.dxf.defpoint2)[:2] != (0.0, 0.0) for item in dimensions)
        )

    def test_builds_world_bindings_from_current_project_geometry(self):
        state = clean_import_state()
        state["converted"]["walers"][0]["world_start"] = [100_123, -200_456]
        state["converted"]["walers"][0]["world_end"] = [103_123, -200_456]
        rows = [
            {
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 3000,
                "EndY": 0,
            }
        ]

        bindings = build_project_member_bindings(
            rows,
            [],
            export_coordinate_system_from_import_state(state),
        )

        binding = bindings[("waler", "W1")]
        self.assertEqual((100_000.0, -200_000.0), binding.world_start)
        self.assertEqual((103_000.0, -200_000.0), binding.world_end)

    def test_added_project_member_needs_no_imported_binding(self):
        rows = [
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0},
            {"WalerID": "W5", "StartX": 10000, "StartY": 0, "EndX": 13000, "EndY": 0},
        ]

        bindings = build_project_member_bindings(
            rows,
            [],
            ExportCoordinateSystem("world"),
        )

        self.assertEqual({("waler", "W1"), ("waler", "W5")}, set(bindings))
        self.assertEqual((10_000.0, 0.0), bindings[("waler", "W5")].world_start)

    def test_updated_same_id_always_uses_current_project_geometry(self):
        rows = [
            {
                "WalerID": "W1",
                "StartX": 1000,
                "StartY": 0,
                "EndX": 4000,
                "EndY": 0,
            }
        ]

        bindings = build_project_member_bindings(
            rows,
            [],
            ExportCoordinateSystem("world"),
        )

        self.assertEqual((1000.0, 0.0), bindings[("waler", "W1")].world_start)
        self.assertEqual((4000.0, 0.0), bindings[("waler", "W1")].world_end)

    def test_world_and_local_coordinate_contract_for_all_member_directions(self):
        walers = [
            {"WalerID": "W1", "StartX": 10, "StartY": 20, "EndX": 3010, "EndY": 20}
        ]
        struts = [
            {"StrutID": "S1", "StartX": 10, "StartY": 20, "EndX": 10, "EndY": 3020}
        ]
        braces = [
            {"BraceID": "B1", "StartX": 10, "StartY": 20, "EndX": 1010, "EndY": 1020}
        ]

        world = build_project_geometry_segments(
            walers, struts, braces, ExportCoordinateSystem("world")
        )
        local = build_project_geometry_segments(
            walers,
            struts,
            braces,
            ExportCoordinateSystem("local", 300_000, 2_700_000),
        )

        self.assertEqual((10.0, 20.0), world[0].world_start)
        self.assertEqual((3010.0, 20.0), world[0].world_end)
        self.assertEqual((300_010.0, 2_700_020.0), local[0].world_start)
        self.assertEqual((300_010.0, 2_703_020.0), local[1].world_end)
        self.assertEqual((301_010.0, 2_701_020.0), local[2].world_end)

    def test_stale_review_uses_current_project_waler_and_brace_geometry(self):
        state = clean_import_state()
        state["project_binding_stale"] = True
        walers = [
            {"WalerID": "W1", "StartX": 0, "StartY": 100, "EndX": 3000, "EndY": 100}
        ]
        struts = [
            {"StrutID": "S1", "StartX": 5100, "StartY": 0, "EndX": 5100, "EndY": 2600}
        ]
        braces = [
            {"BraceID": "B1", "StartX": 200, "StartY": 0, "EndX": 1200, "EndY": 1000}
        ]
        output_path = self.temp_path / "same-length-updates.dxf"

        report = export_results_to_dxf(
            output_path,
            basic_plans(),
            walers,
            struts,
            braces,
            basic_coordinate(),
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_state=state,
        )

        document = ezdxf.readfile(output_path)
        project_lines = {}
        for entity in document.modelspace().query("LINE"):
            if not entity.has_xdata(APP_ID):
                continue
            values = tuple(tag.value for tag in entity.get_xdata(APP_ID))
            if values[:2] == ("clean_dxf_export_v1", "project_geometry"):
                project_lines[(values[2], values[3])] = entity
        self.assertEqual(3, report.project_geometry_count)
        self.assertEqual(
            (100_000.0, -199_900.0),
            tuple(project_lines[("waler", "W1")].dxf.start)[:2],
        )
        self.assertEqual(
            (105_100.0, -200_000.0),
            tuple(project_lines[("strut", "S1")].dxf.start)[:2],
        )
        self.assertEqual(
            (100_200.0, -200_000.0),
            tuple(project_lines[("brace", "B1")].dxf.start)[:2],
        )
        self.assertEqual(PROJECT_WALER_LAYER, project_lines[("waler", "W1")].dxf.layer)
        self.assertEqual(PROJECT_STRUT_LAYER, project_lines[("strut", "S1")].dxf.layer)
        self.assertEqual(PROJECT_BRACE_LAYER, project_lines[("brace", "B1")].dxf.layer)
        self.assertTrue(
            {role for role, _count in report.background_counts}.isdisjoint(
                {"waler", "strut", "brace"}
            )
        )
        modelspace_lines = {
            (tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2])
            for entity in document.modelspace().query("LINE")
        }
        self.assertNotIn(
            ((100_000.0, -200_000.0), (103_000.0, -200_000.0)),
            modelspace_lines,
        )
        self.assertNotIn(
            ((105_000.0, -200_000.0), (105_000.0, -197_400.0)),
            modelspace_lines,
        )
        self.assertNotIn(
            ((100_000.0, -200_000.0), (101_000.0, -199_000.0)),
            modelspace_lines,
        )

        waler_dimensions = []
        strut_jacks = []
        for entity in document.modelspace():
            if not entity.has_xdata(APP_ID):
                continue
            values = tuple(tag.value for tag in entity.get_xdata(APP_ID))
            if values[:3] == ("dxf_result_export_v1", "waler", "W1"):
                waler_dimensions.append(entity)
            if values[:3] == ("dxf_result_export_v1", "strut", "S1") and entity.dxftype() == "INSERT":
                strut_jacks.append(entity)
        self.assertEqual(
            (100_000.0, -199_900.0),
            tuple(waler_dimensions[0].dxf.defpoint2)[:2],
        )
        self.assertEqual((105_100.0, -199_000.0), tuple(strut_jacks[0].dxf.insert)[:2])
        self.assertAlmostEqual(90.0, strut_jacks[0].dxf.rotation, places=6)

    def test_added_waler_strut_and_brace_export_without_converted_members(self):
        state = clean_import_state()
        walers = [
            {"WalerID": "W16", "StartX": 0, "StartY": 500, "EndX": 3000, "EndY": 500}
        ]
        struts = [
            {"StrutID": "S16", "StartX": 6000, "StartY": 0, "EndX": 6000, "EndY": 2600}
        ]
        braces = [
            {"BraceID": "B16", "StartX": 0, "StartY": 2000, "EndX": 1000, "EndY": 3000}
        ]
        plans = (
            MemberExportPlan("W16", "waler", (ExportPiece("steel", 3000),)),
            MemberExportPlan(
                "S16",
                "strut",
                (ExportPiece("steel", 2000), ExportPiece("jack", 600)),
            ),
        )
        output_path = self.temp_path / "added-members.dxf"

        report = export_results_to_dxf(
            output_path,
            plans,
            walers,
            struts,
            braces,
            basic_coordinate(),
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_state=state,
        )

        self.assertTrue(output_path.is_file())
        self.assertEqual(3, report.project_geometry_count)
        self.assertEqual(2, report.member_count)
        document = ezdxf.readfile(output_path)
        project_ids = {
            tuple(tag.value for tag in entity.get_xdata(APP_ID))[3]
            for entity in document.modelspace().query("LINE")
            if entity.has_xdata(APP_ID)
            and tuple(tag.value for tag in entity.get_xdata(APP_ID))[:2]
            == ("clean_dxf_export_v1", "project_geometry")
        }
        self.assertEqual({"W16", "S16", "B16"}, project_ids)

    def test_stale_binding_and_old_review_errors_do_not_block_current_export(self):
        state = clean_import_state()
        state["project_binding_stale"] = True
        state["validation_messages"] = [
            {"severity": "critical", "message": "old recognition warning"}
        ]

        report = export_basic(
            self.temp_path / "stale-review-state.dxf",
            state=state,
        )

        self.assertEqual(2, report.member_count)
        self.assertEqual(0, report.final_audit.error_count)

    def test_result_only_waler_uses_identity_and_omits_unused_layers(self):
        walers = [
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0}
        ]
        output_path = self.temp_path / "waler-result-only.dxf"

        report = export_results_to_dxf(
            output_path,
            (MemberExportPlan("W1", "waler", (ExportPiece("steel", 3000),)),),
            walers,
            [],
            [],
            ExportCoordinateSystem("world"),
            export_mode=DXFExportMode.RESULT_ONLY,
        )

        self.assertTrue(output_path.is_file())
        self.assertEqual(DXFExportMode.RESULT_ONLY, report.export_mode)
        self.assertEqual("world", report.coordinate_mode)
        self.assertEqual(0, report.background_segment_count)
        self.assertEqual(0, report.project_geometry_count)
        document = ezdxf.readfile(output_path)
        self.assertIn(RESULT_WALER_LAYER, document.layers)
        self.assertNotIn(RESULT_SUPPORT_LAYER, document.layers)
        self.assertNotIn(PROJECT_WALER_LAYER, document.layers)
        self.assertNotIn(PROJECT_STRUT_LAYER, document.layers)
        self.assertNotIn(PROJECT_BRACE_LAYER, document.layers)
        dimensions = list(document.modelspace().query("DIMENSION"))
        self.assertEqual((0.0, 0.0), tuple(dimensions[0].dxf.defpoint2)[:2])
        self.assertNotIn(JACK_BLOCK_NAME, document.blocks)
        self.assertIn("使用目前 Project 座標直接輸出", report.merge_guidance)
        self.assertIn("未對齊任何來源圖面", report.merge_guidance)
        self.assertIn("需由使用者自行定位", report.merge_guidance)

    def test_result_only_support_creates_only_support_layer_and_required_jack(self):
        struts = [
            {
                "StrutID": "S1",
                "StartX": 1000,
                "StartY": 2000,
                "EndX": 4000,
                "EndY": 2000,
            }
        ]
        plan = MemberExportPlan(
            "S1",
            "strut",
            (ExportPiece("steel", 2400), ExportPiece("jack", 600)),
        )
        output_path = self.temp_path / "support-result-only.dxf"

        report = export_results_to_dxf(
            output_path,
            (plan,),
            [],
            struts,
            [],
            ExportCoordinateSystem("world"),
            export_mode=DXFExportMode.RESULT_ONLY,
        )

        document = ezdxf.readfile(output_path)
        self.assertEqual(DXFExportMode.RESULT_ONLY, report.export_mode)
        self.assertNotIn(RESULT_WALER_LAYER, document.layers)
        self.assertIn(RESULT_SUPPORT_LAYER, document.layers)
        self.assertIn(JACK_BLOCK_NAME, document.blocks)
        inserts = [
            entity
            for entity in document.modelspace().query("INSERT")
            if entity.dxf.name == JACK_BLOCK_NAME
        ]
        self.assertEqual(1, len(inserts))
        self.assertEqual(RESULT_SUPPORT_LAYER, inserts[0].dxf.layer)

    def test_invalid_warning_is_equivalent_in_both_modes_and_uses_cjk_style(self):
        walers = [
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0}
        ]
        plan = MemberExportPlan(
            "W1",
            "waler",
            (ExportPiece("steel", 3000),),
            result_id="W1-invalid",
            valid=False,
            reasons=("鋼材總長不足", "接頭落入禁止區"),
        )
        documents = []
        for mode in (DXFExportMode.SOURCE_BACKED, DXFExportMode.RESULT_ONLY):
            output_path = self.temp_path / f"warning-{mode.value}.dxf"
            export_results_to_dxf(
                output_path,
                (plan,),
                walers,
                [],
                [],
                ExportCoordinateSystem("world"),
                export_mode=mode,
                background_state=(clean_import_state() if mode is DXFExportMode.SOURCE_BACKED else None),
            )
            documents.append(ezdxf.readfile(output_path))

        warning_snapshots = []
        for document in documents:
            self.assertIn(WARNING_INVALID_RESULT_LAYER, document.layers)
            self.assertEqual(
                1,
                abs(int(document.layers.get(WARNING_INVALID_RESULT_LAYER).dxf.color)),
            )
            style = document.styles.get(WARNING_TEXT_STYLE)
            self.assertEqual(WARNING_FONT_FILE, style.dxf.font)
            self.assertEqual(
                WARNING_FONT_FAMILY,
                style.get_extended_font_data()[0],
            )
            warnings = list(
                document.modelspace().query(
                    f'MTEXT[layer=="{WARNING_INVALID_RESULT_LAYER}"]'
                )
            )
            self.assertEqual(1, len(warnings))
            warning = warnings[0]
            self.assertEqual(WARNING_TEXT_STYLE, warning.dxf.style)
            self.assertEqual(256, warning.dxf.color)
            self.assertIn("W1", warning.plain_text())
            self.assertIn("鋼材總長不足", warning.plain_text())
            self.assertIn("接頭落入禁止區", warning.plain_text())
            expected_anchor = (1500.0, WARNING_TEXT_OFFSET_MM)
            self.assertLessEqual(
                math.dist(tuple(warning.dxf.insert)[:2], expected_anchor),
                WARNING_ANCHOR_TOLERANCE_MM,
            )
            warning_snapshots.append(
                (warning.plain_text(), tuple(warning.dxf.insert)[:2])
            )
        self.assertEqual(warning_snapshots[0], warning_snapshots[1])

    def test_double_support_invalid_warnings_are_separate_and_deterministic(self):
        struts = [
            {"StrutID": "S1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0},
            {"StrutID": "S2", "StartX": 0, "StartY": 100, "EndX": 3000, "EndY": 100},
        ]
        plans = (
            MemberExportPlan(
                "S2",
                "strut",
                (ExportPiece("steel", 3000),),
                result_id="Z1",
                valid=False,
                reasons=("S2 待修正",),
            ),
            MemberExportPlan(
                "S1",
                "strut",
                (ExportPiece("steel", 3000),),
                result_id="Z1",
                valid=False,
                reasons=("S1 待修正",),
            ),
        )

        snapshots = []
        for index, ordered_plans in enumerate((plans, tuple(reversed(plans)))):
            output_path = self.temp_path / f"double-support-{index}.dxf"
            export_results_to_dxf(
                output_path,
                ordered_plans,
                [],
                struts,
                [],
                ExportCoordinateSystem("world"),
                export_mode=DXFExportMode.RESULT_ONLY,
            )
            document = ezdxf.readfile(output_path)
            warnings = list(
                document.modelspace().query(
                    f'MTEXT[layer=="{WARNING_INVALID_RESULT_LAYER}"]'
                )
            )
            self.assertEqual(2, len(warnings))
            by_member = {}
            for warning in warnings:
                values = tuple(tag.value for tag in warning.get_xdata(APP_ID))
                by_member[str(values[2])] = tuple(warning.dxf.insert)[:2]
            self.assertEqual({"S1", "S2"}, set(by_member))
            self.assertNotEqual(by_member["S1"], by_member["S2"])
            snapshots.append(by_member)
        self.assertEqual(snapshots[0], snapshots[1])

    def test_legal_results_do_not_create_warning_layer_or_style(self):
        output_path = self.temp_path / "all-legal.dxf"
        export_basic(output_path)

        document = ezdxf.readfile(output_path)
        self.assertNotIn(WARNING_INVALID_RESULT_LAYER, document.layers)
        self.assertNotIn(WARNING_TEXT_STYLE, document.styles)

    def test_export_context_uses_only_import_state_presence(self):
        mode, coordinate = resolve_dxf_export_context(None)
        self.assertEqual(DXFExportMode.RESULT_ONLY, mode)
        self.assertEqual(ExportCoordinateSystem("world"), coordinate)

        review_state = clean_import_state()
        review_state["dxf_workflow_status"] = "REVIEW"
        mode, coordinate = resolve_dxf_export_context(review_state)
        self.assertEqual(DXFExportMode.SOURCE_BACKED, mode)
        self.assertEqual("local", coordinate.mode)

        for state in ({}, {"dxf_workflow_status": "REVIEW"}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(DXFResultExportError, "Project → World"):
                    resolve_dxf_export_context(state)

    def test_missing_coordinate_metadata_has_clear_error(self):
        for state in (None, {}, {"coordinate_system": {}}):
            with self.subTest(state=state):
                with self.assertRaisesRegex(
                    DXFResultExportError,
                    "Project → World|Project 座標模式",
                ):
                    export_coordinate_system_from_import_state(state)

    def test_invalid_project_geometry_is_rejected(self):
        invalid_rows = (
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 0, "EndY": 0},
            {"WalerID": "W1", "StartX": math.nan, "StartY": 0, "EndX": 1, "EndY": 0},
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": math.inf, "EndY": 0},
        )
        for row in invalid_rows:
            with self.subTest(row=row):
                with self.assertRaises(DXFResultExportError):
                    build_project_geometry_segments(
                        [row], [], [], ExportCoordinateSystem("world")
                    )

    def test_continuous_wall_background_is_kept_and_bad_context_is_skipped(self):
        state = clean_import_state()
        state["source_geometry"].extend(
            [
                {
                    "role": "continuous_wall",
                    "source_handle": "CW1",
                    "points": [[90_000, -210_000], [110_000, -210_000]],
                    "closed": False,
                    "source_layer": "L-SITE-WALL",
                },
                {
                    "role": "auxiliary",
                    "source_handle": "BAD",
                    "points": [["not-a-number", 0], [1, 1]],
                    "closed": False,
                    "source_layer": "AUX_BAD",
                },
            ]
        )

        report = export_basic(self.temp_path / "optional-background.dxf", state=state)

        counts = dict(report.background_counts)
        self.assertEqual(1, counts["continuous_wall"])
        self.assertTrue(any("已略過" in warning for warning in report.warnings))
        self.assertEqual(0, report.final_audit.error_count)

    def test_rejects_conflicting_or_incomplete_plans_before_writing(self):
        conflict = (
            MemberExportPlan("W1", "waler", (ExportPiece("steel", 3000),), result_id="A"),
            MemberExportPlan("W1", "waler", (ExportPiece("steel", 3000),), result_id="B"),
        )
        with self.assertRaisesRegex(DXFResultExportError, "W1"):
            export_basic(self.temp_path / "conflict.dxf", conflict)

        short = MemberExportPlan(
            "W1", "waler", (ExportPiece("steel", 2500),), result_id="short"
        )
        with self.assertRaisesRegex(DXFResultExportError, "配置總長"):
            export_basic(self.temp_path / "short.dxf", (short,))

    def test_main_collects_only_currently_visible_result_plans(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.result_items = {
            "W1-plan-1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "selected_plan": {
                        "pieces": [("steel", 2900), ("shim", 50)],
                        "gap": 50,
                    },
                },
            },
            "W1-plan-2": {
                "type": "waler",
                "visible": False,
                "result": {
                    "waler_id": "W1",
                    "selected_plan": {"pieces": [("steel", 3000)]},
                },
            },
            "zone-plan-1": {
                "type": "support",
                "visible": True,
                "support_visibility": {"S1": True, "S2": False},
                "result": SimpleNamespace(
                    plans=[
                        SimpleNamespace(
                            support_id="S1",
                            pieces=[("steel", 1900), ("jack", 600)],
                            gap=100,
                        ),
                        SimpleNamespace(
                            support_id="S2",
                            pieces=[("steel", 2000), ("jack", 600)],
                            gap=0,
                        ),
                    ]
                ),
            },
        }

        plans = app._visible_dxf_export_plans()

        self.assertEqual(
            [("waler", "W1"), ("strut", "S1")],
            [(plan.role, plan.member_id) for plan in plans],
        )
        self.assertEqual(ExportPiece("shim", 50.0), plans[0].pieces[-1])
        self.assertEqual(ExportPiece("jack", 600.0), plans[1].pieces[-1])
        self.assertTrue(all(not plan.valid for plan in plans))
        self.assertTrue(
            all(plan.reasons == ("未提供不合法原因",) for plan in plans)
        )


if __name__ == "__main__":
    unittest.main()
