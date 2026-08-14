from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from dxf_result_export import (
    APP_ID,
    CLEAN_DXF_ACAD_VERSION,
    JACK_BLOCK_NAME,
    RESULT_SUPPORT_LAYER,
    RESULT_WALER_LAYER,
    DXFResultExportError,
    ExportPiece,
    MemberBinding,
    MemberExportPlan,
    build_member_bindings,
    export_results_to_dxf,
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


def basic_bindings() -> dict[tuple[str, str], MemberBinding]:
    return {
        ("waler", "W1"): MemberBinding(
            "W1", "waler", "WALER_SOURCE", (100_000, -200_000), (103_000, -200_000)
        ),
        ("strut", "S1"): MemberBinding(
            "S1", "strut", "STRUT_SOURCE", (105_000, -200_000), (105_000, -197_400)
        ),
    }


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


class DXFResultExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_builds_clean_r2018_world_coordinate_result_dxf(self):
        output_path = self.temp_path / "中文 空格 clean result.dxf"

        report = export_results_to_dxf(
            clean_import_state(),
            output_path,
            basic_plans(),
            basic_bindings(),
        )

        self.assertTrue(output_path.is_file())
        self.assertEqual(CLEAN_DXF_ACAD_VERSION, ezdxf.readfile(output_path).dxfversion)
        self.assertEqual("mm", report.coordinate_units)
        self.assertEqual("local", report.coordinate_mode)
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

    def test_reconstructs_every_required_background_role_and_deduplicates_lines(self):
        output_path = self.temp_path / "background.dxf"
        report = export_results_to_dxf(
            clean_import_state(), output_path, basic_plans(), basic_bindings()
        )

        self.assertEqual(
            {"waler", "strut", "brace", "corner_brace", "column", "beam", "auxiliary"},
            {role for role, _count in report.background_counts},
        )
        # 1+1+1+1+5(column outline+confirmed center)+2+1
        self.assertEqual(12, report.background_segment_count)
        exported = ezdxf.readfile(output_path)
        background_lines = [
            entity
            for entity in exported.modelspace().query("LINE")
            if entity.has_xdata(APP_ID)
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
        binding = MemberBinding("S1", "strut", "STRUT_SOURCE", start, end)
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
            state,
            output_path,
            (plan,),
            {("strut", "S1"): binding},
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
        binding = MemberBinding("S1", "strut", "STRUT_SOURCE", start, end)
        plan = MemberExportPlan(
            "S1",
            "strut",
            (ExportPiece("steel", 1400), ExportPiece("jack", 600), ExportPiece("steel", 1000)),
            result_id="diagonal",
        )
        output_path = self.temp_path / "diagonal-local-render.dxf"

        report = export_results_to_dxf(
            state,
            output_path,
            (plan,),
            {("strut", "S1"): binding},
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

    def test_builds_world_bindings_from_final_confirmed_geometry(self):
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

        bindings = build_member_bindings(state, rows, [])

        binding = bindings[("waler", "W1")]
        self.assertEqual((100_123.0, -200_456.0), binding.world_start)
        self.assertEqual((103_123.0, -200_456.0), binding.world_end)

    def test_append_id_collision_does_not_bind_old_row_to_new_geometry(self):
        dxf_state = {
            "coordinate_system": {"mode": "world"},
            "converted": {
                "walers": [
                    {
                        "id": "W1",
                        "source_layer": "NEW_DXF_WALER",
                        "start": [10000, 0],
                        "end": [13000, 0],
                    }
                ],
                "struts": [],
            },
        }
        rows = [
            {"WalerID": "W1", "StartX": 0, "StartY": 0, "EndX": 3000, "EndY": 0},
            {"WalerID": "W5", "StartX": 10000, "StartY": 0, "EndX": 13000, "EndY": 0},
        ]

        bindings = build_member_bindings(dxf_state, rows, [])

        self.assertNotIn(("waler", "W1"), bindings)
        self.assertEqual("NEW_DXF_WALER", bindings[("waler", "W5")].layer)

    def test_rejects_conflicting_or_incomplete_plans_before_writing(self):
        bindings = basic_bindings()
        conflict = (
            MemberExportPlan("W1", "waler", (ExportPiece("steel", 3000),), result_id="A"),
            MemberExportPlan("W1", "waler", (ExportPiece("steel", 3000),), result_id="B"),
        )
        with self.assertRaisesRegex(DXFResultExportError, "W1"):
            export_results_to_dxf(clean_import_state(), self.temp_path / "conflict.dxf", conflict, bindings)

        short = MemberExportPlan(
            "W1", "waler", (ExportPiece("steel", 2500),), result_id="short"
        )
        with self.assertRaisesRegex(DXFResultExportError, "配置總長"):
            export_results_to_dxf(clean_import_state(), self.temp_path / "short.dxf", (short,), bindings)

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


if __name__ == "__main__":
    unittest.main()
