import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bracing_optimizer.infrastructure.cad_builder import (
    DEFAULT_TEMP_PATH,
    EVENT_FILE_NAME,
    CadEventMapper,
    CadEventReader,
    TABLE_SPECS,
    TempEventWatcher,
)
from main import SupportInputApp
from bracing_optimizer.application.project_data import TABLE_COLUMNS, ProjectDataModel
from bracing_optimizer.infrastructure.project_persistence import ProjectPersistenceError
from bracing_optimizer.infrastructure.project_persistence import DxfCompatibilityChecker
from dxf_import.dialog import DXFImportDialog
from dxf_import.models import CoordinateSystem


PROJECT_DIR = Path(__file__).resolve().parents[1]


class CADBuilderIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.event_path = self.temp_path / "cad_builder_temp.json"
        self.watcher = TempEventWatcher(self.event_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_event(self, event):
        self.event_path.write_text(
            json.dumps(event, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def update_event(
        *,
        event_id="update-s5",
        target_id="S5",
        start=(100, 0),
        end=(100, 1000),
        beams="250,750",
        columns="500",
    ):
        return {
            "event_id": event_id,
            "type": "strut",
            "operation": "update",
            "coordinate_space": "WCS",
            "target_id": target_id,
            "data": {
                "StartX": start[0],
                "StartY": start[1],
                "EndX": end[0],
                "EndY": end[1],
                "BeamPositions": beams,
                "ColumnPositions": columns,
            },
        }

    @staticmethod
    def linear_update_event(
        member_type,
        target_id,
        *,
        event_id=None,
        start=(100, 0),
        end=(1900, 0),
        **extra_data,
    ):
        return {
            "event_id": event_id or f"update-{member_type}-{target_id}",
            "type": member_type,
            "operation": "update",
            "coordinate_space": "WCS",
            "target_id": target_id,
            "data": {
                "StartX": start[0],
                "StartY": start[1],
                "EndX": end[0],
                "EndY": end[1],
                **extra_data,
            },
        }

    @staticmethod
    def project_geometry():
        walers = [
            {
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 2000,
                "EndY": 0,
            },
            {
                "WalerID": "W2",
                "StartX": 0,
                "StartY": 1000,
                "EndX": 2000,
                "EndY": 1000,
            },
        ]
        strut = {
            "StrutID": "S5",
            "SharedLayoutGroup": "G1",
            "FromWaler": "W1",
            "ToWaler": "W2",
            "StartX": 100,
            "StartY": 0,
            "EndX": 100,
            "EndY": 1000,
            "material_spec": "H400x400",
            "BeamPositions": "100,900",
            "ColumnPositions": "300",
            "AssociatedColumnIDs": "C1",
            "AssociatedBeamIDs": "BM1",
            "FromBraceToWalerStartLen": 100,
            "FromBraceToWalerEndLen": 200,
            "ToBraceToWalerStartLen": 300,
            "ToBraceToWalerEndLen": 400,
            "TargetJackRegion": 3,
            "Zoning": "Z9",
        }
        return walers, strut

    @staticmethod
    def brace_row():
        return {
            "BraceID": "B2",
            "FromWaler": "W1",
            "ToWaler": "W2",
            "StartX": 200,
            "StartY": 0,
            "EndX": 300,
            "EndY": 1000,
        }

    @staticmethod
    def dxf_state(
        *,
        duplicate=False,
        local=False,
        include_strut=True,
        brace=None,
        duplicate_brace=False,
    ):
        strut = {
            "id": "DXF-S1",
            "start": [100, 0],
            "end": [100, 1000],
            "local_start": [100, 0],
            "local_end": [100, 1000],
            "world_start": [10100, 20000] if local else [100, 0],
            "world_end": [10100, 21000] if local else [100, 1000],
            "source_layer": "STRUT_LAYER",
            "source_handles": ["A1", "A2"],
            "recognition_method": "outline_centerline",
            "beam_positions": [100, 900],
            "column_positions": [300],
            "associated_columns": ["C1"],
            "associated_beams": ["BM1"],
            "selection_source": "auto",
        }
        struts = [strut] if include_strut else []
        if duplicate:
            duplicate_strut = copy.deepcopy(strut)
            duplicate_strut["id"] = "DXF-S2"
            struts.append(duplicate_strut)
        braces = []
        if brace is not None:
            brace_binding = {
                "id": "DXF-B2",
                "start": [brace["StartX"], brace["StartY"]],
                "end": [brace["EndX"], brace["EndY"]],
                "local_start": [brace["StartX"], brace["StartY"]],
                "local_end": [brace["EndX"], brace["EndY"]],
                "world_start": (
                    [brace["StartX"] + 10000, brace["StartY"] + 20000]
                    if local
                    else [brace["StartX"], brace["StartY"]]
                ),
                "world_end": (
                    [brace["EndX"] + 10000, brace["EndY"] + 20000]
                    if local
                    else [brace["EndX"], brace["EndY"]]
                ),
                "from_waler": brace["FromWaler"],
                "to_waler": brace["ToWaler"],
                "source_layer": "BRACE_LAYER",
                "source_handles": ["B1", "B2"],
                "recognition_method": "outline_centerline",
                "selection_source": "auto",
            }
            braces.append(brace_binding)
            if duplicate_brace:
                duplicate_binding = copy.deepcopy(brace_binding)
                duplicate_binding["id"] = "DXF-B3"
                braces.append(duplicate_binding)
        return {
            "coordinate_system": {
                "mode": "local" if local else "world",
                "origin_x": 10000 if local else 0,
                "origin_y": 20000 if local else 0,
                "source": "test",
            },
            "converted": {
                "walers": [],
                "struts": struts,
                "braces": braces,
                "columns": [],
                "beams": [],
                "corner_braces": [],
            },
            "source_geometry": [
                {
                    "role": "strut",
                    "source_handle": "A1",
                    "source_layer": "STRUT_LAYER",
                    "points": [[90, 0], [90, 1000]],
                    "closed": False,
                }
            ],
            "validation_messages": [],
            "component_associations": [],
            "beam_crossings": [],
        }

    def load_with_solver(self, case_name):
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_cases_dir = self.temp_path
        app.result_items = {}
        app.project_result = None
        app.last_calculated_time = None
        app.current_project_path = None
        app.solver_memory = {}
        app.support_candidate_cache = {}
        app._refresh_tree = lambda _name: None
        app._refresh_results_tree = lambda **_kwargs: None
        app._refresh_project_case_list = lambda **_kwargs: None
        app.update_preview = lambda **_kwargs: None
        app.show_result = lambda _text: None
        app.load_project_case(case_name, silent=True)
        return app

    def main_app_for_cad_import(self, *, walers=None):
        app = SupportInputApp.__new__(SupportInputApp)
        app.walers = list(walers if walers is not None else [{"WalerID": "W2"}])
        app.struts = []
        app.braces = []
        app.result_items = {"old-result": {}}
        app.project_result = {"old-project-result": True}
        app.last_calculated_time = "2026-09-12T00:00:00"
        app.solver_memory = {"old-memory": {}}
        app.support_candidate_cache = {"old-candidate": {}}
        app.cad_event_mapper = CadEventMapper()
        app.cad_event_watcher = TempEventWatcher(self.event_path)
        app.cad_import_status = "waiting"
        app.cad_last_event = None
        app.cad_last_error = None
        app.dxf_last_import_debug = None
        app.dxf_compatibility_checker = DxfCompatibilityChecker()
        app.last_dxf_compatibility_report = None
        app.project_dirty = False
        app.table_columns = {
            "walers": ["WalerID"],
            "struts": ["StrutID"],
            "braces": ["BraceID"],
        }
        app.treeviews = {}
        app.refreshed_tables = []
        app.preview_update_count = 0
        app.result_refresh_count = 0
        app.selected_rows = []
        app._refresh_tree = app.refreshed_tables.append
        app._refresh_results_tree = lambda: setattr(
            app,
            "result_refresh_count",
            app.result_refresh_count + 1,
        )
        app.update_preview = lambda **_kwargs: setattr(
            app,
            "preview_update_count",
            app.preview_update_count + 1,
        )
        app._mark_project_dirty = lambda _reason: setattr(
            app,
            "project_dirty",
            True,
        )
        app._select_input_row = lambda table, index: app.selected_rows.append(
            (table, index)
        )
        return app

    def test_builder_columns_match_solver_columns(self):
        columns = TABLE_COLUMNS
        self.assertIs(SupportInputApp.TABLE_COLUMNS, TABLE_COLUMNS)
        self.assertEqual(tuple(columns["walers"]), TABLE_SPECS["walers"]["columns"])
        self.assertEqual(tuple(columns["struts"]), TABLE_SPECS["struts"]["columns"])
        self.assertEqual(tuple(columns["braces"]), TABLE_SPECS["braces"]["columns"])

    def test_main_properties_reference_one_project_data_model(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.project_data = ProjectDataModel()
        app.walers = [{"WalerID": "W1"}]
        app.struts = [{"StrutID": "S1"}]

        self.assertIs(app.walers, app.project_data.walers)
        self.assertIs(app.struts, app.project_data.struts)
        self.assertEqual(app.walers[0]["StartX"], "")
        self.assertEqual(app.struts[0]["TargetJackRegion"], 2)

    def test_project_data_replaces_one_row_without_replacing_owned_list(self):
        model = ProjectDataModel(struts=[{"StrutID": "S5", "StartX": 0}])
        owned_rows = model.struts

        replaced = model.replace_row(
            "struts",
            0,
            {**model.struts[0], "StartX": 100},
        )

        self.assertIs(model.struts, owned_rows)
        self.assertIs(model.struts[0], replaced)
        self.assertEqual(model.struts[0]["StrutID"], "S5")
        self.assertEqual(model.struts[0]["StartX"], 100)

    def test_main_result_messages_append_instead_of_overwriting(self):
        class FakeResultText:
            def __init__(self):
                self.content = ""
                self.states = []
                self.last_seen = None

            def configure(self, **kwargs):
                self.states.append(kwargs.get("state"))

            def get(self, _start, _end):
                return self.content

            def insert(self, _position, text):
                self.content += text

            def see(self, position):
                self.last_seen = position

        app = SupportInputApp.__new__(SupportInputApp)
        app.result_text = FakeResultText()

        app.show_result("第一個結果")
        app.show_result("第二個結果")

        self.assertIn("第一個結果", app.result_text.content)
        self.assertIn("第二個結果", app.result_text.content)
        self.assertLess(
            app.result_text.content.index("第一個結果"),
            app.result_text.content.index("第二個結果"),
        )
        self.assertIn("-" * 60, app.result_text.content)
        self.assertEqual(app.result_text.last_seen, "end")
        self.assertEqual(app.result_text.states[-1], "disabled")

    def test_autolisp_and_builder_share_the_same_event_contract(self):
        lisp_source = (PROJECT_DIR / "cad_builder.lsp").read_text(encoding="utf-8")
        self.assertEqual(DEFAULT_TEMP_PATH.parent, Path(tempfile.gettempdir()))
        self.assertEqual(DEFAULT_TEMP_PATH.name, EVENT_FILE_NAME)
        self.assertEqual(TempEventWatcher().temp_path, DEFAULT_TEMP_PATH)
        self.assertIn(f'"{EVENT_FILE_NAME}"', lisp_source)
        for command in (
            "ADDWALER",
            "UPDWALER",
            "ADDSTRUT",
            "UPDSTRUT",
            "ADDBRACE",
            "UPDBRACE",
            "SUPSTATUS",
            "SUPCLEAR",
        ):
            self.assertIn(f"(defun c:{command}", lisp_source)
        for command in (
            "CADBUILDER",
            "CBWALER",
            "CBSTRUT",
            "CBBRACE",
            "CBSTATUS",
            "ADDSUPPORT",
        ):
            self.assertNotIn(f"(defun c:{command}", lisp_source)
        self.assertNotIn("(entsel", lisp_source)
        self.assertNotIn("(vl-string-right-trim", lisp_source)
        self.assertIn("(getpoint", lisp_source)
        self.assertIn("(trans point 1 0)", lisp_source)
        self.assertIn("(defun cb:projection-distance", lisp_source)
        self.assertIn("(defun cb:round-integer", lisp_source)
        lisp_source.encode("ascii")
        self.assertIn('(getpoint (strcat "\\nPick "', lisp_source)
        self.assertIn('(getpoint p1-ucs (strcat "\\nPick "', lisp_source)
        self.assertIn('(cb:capture-simple "waler" "Waler")', lisp_source)
        self.assertIn(
            '(cb:capture-linear-update "waler" "Waler" "WalerID")',
            lisp_source,
        )
        self.assertIn(
            '(cb:capture-linear-update "brace" "Brace" "BraceID")',
            lisp_source,
        )
        self.assertIn('(cb:read-target-id "StrutID")', lisp_source)
        self.assertEqual(lisp_source.count("(defun cb:event-json"), 1)
        self.assertEqual(lisp_source.count("(defun cb:capture-linear-update"), 1)
        self.assertNotIn("UPDCORNERBRACE", lisp_source)
        self.assertIn("Pick beam positions? [Yes/No] <No>:", lisp_source)
        self.assertIn("Pick column positions? [Yes/No] <No>:", lisp_source)
        self.assertIn("selected point is outside the strut range", lisp_source)
        self.assertIn('(getvar "CDATE")', lisp_source)
        self.assertIn("MILLISECS", lisp_source)
        self.assertIn("cb:pending-message", lisp_source)
        self.assertIn("(defun cb:cancel-event-json", lisp_source)
        self.assertIn('\\"operation\\":\\"cancel\\"', lisp_source)
        self.assertIn("(findfile", lisp_source)
        self.assertNotIn("cb:temp-path", lisp_source)
        self.assertNotIn("(vl-file-delete", lisp_source)
        self.assertNotIn("(vl-file-rename", lisp_source)
        self.assertIn("(cb:write-text-file event-path content)", lisp_source)
        self.assertIn('\\"TargetJackRegion\\":2', lisp_source)
        for correct_expression in (
            '(if (or (null temp-dir) (= temp-dir "") (= temp-dir " "))',
            '(if (= station-text "")',
            '(if (= answer "Yes")',
            '(if (= extra-fields "")',
        ):
            self.assertIn(correct_expression, lisp_source)
        for invalid_expression in (
            '(if (or (null temp-dir) temp-dir ""))',
            '(if station-text "")',
            '(if answer "Yes")',
            '(if extra-fields "")',
        ):
            self.assertNotIn(invalid_expression, lisp_source)
        for field in (
            "event_id",
            "type",
            "operation",
            "coordinate_space",
            "target_id",
            "StartX",
            "StartY",
            "EndX",
            "EndY",
            "BeamPositions",
            "ColumnPositions",
            "TargetJackRegion",
        ):
            self.assertIn(f'\\"{field}\\"', lisp_source)

    def test_autolisp_parentheses_strings_and_json_examples_are_valid(self):
        lisp_source = (PROJECT_DIR / "cad_builder.lsp").read_text(encoding="utf-8")
        balance = 0
        in_string = False
        escaped = False
        in_comment = False
        for character in lisp_source:
            if in_comment:
                if character == "\n":
                    in_comment = False
                continue
            if in_string:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    in_string = False
                continue
            if character == ";":
                in_comment = True
            elif character == '"':
                in_string = True
            elif character == "(":
                balance += 1
            elif character == ")":
                balance -= 1
                self.assertGreaterEqual(balance, 0)
        self.assertFalse(in_string)
        self.assertEqual(balance, 0)

        examples_path = PROJECT_DIR / "cad_bridge_event_examples.json"
        examples_text = examples_path.read_text(encoding="utf-8")
        examples = json.loads(examples_text)
        expected_types = {
            "ADDWALER": "waler",
            "UPDWALER": "waler",
            "ADDSTRUT": "strut",
            "UPDSTRUT": "strut",
            "ADDBRACE": "brace",
            "UPDBRACE": "brace",
            "SUPCLEAR": "control",
        }
        for command, event_type in expected_types.items():
            encoded_event = json.dumps(examples[command], ensure_ascii=False)
            parsed_event = json.loads(encoded_event)
            self.assertEqual(parsed_event["type"], event_type)
            self.assertIn(parsed_event["operation"], {"add", "update", "cancel"})
            self.assertEqual(parsed_event["coordinate_space"], "WCS")
            self.assertIsInstance(parsed_event["event_id"], str)
            self.assertIsInstance(parsed_event["data"], dict)
            if parsed_event["operation"] == "update":
                self.assertTrue(parsed_event["target_id"])

    def test_strut_event_maps_new_position_fields_without_legacy_columns(self):
        event = {
            "event_id": "new-strut-fields",
            "type": "strut",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {
                "StartX": 0,
                "StartY": 0,
                "EndX": 12000,
                "EndY": 0,
                "BeamPositions": "3500,7000,10500",
                "ColumnPositions": "5000,10000",
                "TargetJackRegion": 2,
            },
        }

        table_name, row = CadEventMapper.map_event(
            event,
            {"walers": [], "struts": [], "braces": []},
        )

        self.assertEqual(table_name, "struts")
        self.assertEqual(row["BeamPositions"], "3500,7000,10500")
        self.assertEqual(row["ColumnPositions"], "5000,10000")
        self.assertEqual(row["TargetJackRegion"], 2)
        for legacy_field in ("Beam1", "Beam2", "Column1", "Column2"):
            self.assertNotIn(legacy_field, row)

    def test_headless_event_reader_and_mapper_do_not_own_project_data(self):
        event = {
            "event_id": "headless-waler",
            "type": "waler",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {"StartX": 1, "StartY": 2, "EndX": 3, "EndY": 4},
        }
        self.event_path.write_text(json.dumps(event), encoding="utf-8")
        loaded_event = CadEventReader.load(self.event_path)
        existing_rows = {
            "walers": [{"WalerID": "W3"}],
            "struts": [],
            "braces": [],
        }

        table_name, row = CadEventMapper.map_event(loaded_event, existing_rows)

        self.assertEqual(table_name, "walers")
        self.assertEqual(row["WalerID"], "W4")
        self.assertEqual(row["StartX"], 1)
        self.assertEqual(existing_rows["walers"], [{"WalerID": "W3"}])

    def test_main_imports_cad_event_directly_and_invalidates_old_solver_state(self):
        app = self.main_app_for_cad_import()
        event = {
            "event_id": "main-direct-waler",
            "type": "waler",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {"StartX": 1, "StartY": 2, "EndX": 3, "EndY": 4},
        }
        self.event_path.write_text(json.dumps(event), encoding="utf-8")

        self.assertTrue(app.read_cad_event())

        self.assertFalse(self.event_path.exists())
        self.assertEqual(len(app.walers), 2)
        self.assertEqual(app.walers[-1]["WalerID"], "W3")
        self.assertEqual(app.refreshed_tables, ["walers"])
        self.assertEqual(app.preview_update_count, 1)
        self.assertEqual(app.result_refresh_count, 1)
        self.assertEqual(app.result_items, {})
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})
        self.assertEqual(app.cad_import_status, "匯入成功：W3")

    def test_update_uses_current_event_stations_when_direction_is_reversed(self):
        walers, strut = self.project_geometry()
        event = self.update_event(
            start=(300, 1000),
            end=(300, 0),
            beams="100,700",
            columns="250",
        )

        mapped = CadEventMapper.map_command(
            event,
            {"walers": walers, "struts": [strut], "braces": []},
        )

        self.assertEqual((mapped.row["StartX"], mapped.row["StartY"]), (300, 0))
        self.assertEqual((mapped.row["EndX"], mapped.row["EndY"]), (300, 1000))
        self.assertEqual(mapped.row["BeamPositions"], "300,900")
        self.assertEqual(mapped.row["ColumnPositions"], "750")
        self.assertEqual(mapped.world_start, (300, 0))
        self.assertEqual(mapped.world_end, (300, 1000))

    def test_update_transforms_wcs_to_project_local_coordinates(self):
        walers, strut = self.project_geometry()
        event = self.update_event(
            start=(10150, 20000),
            end=(10150, 21000),
        )

        mapped = CadEventMapper.map_command(
            event,
            {"walers": walers, "struts": [strut], "braces": []},
            coordinate_system=CoordinateSystem("local", 10000, 20000, "test"),
        )

        self.assertEqual((mapped.row["StartX"], mapped.row["StartY"]), (150, 0))
        self.assertEqual((mapped.row["EndX"], mapped.row["EndY"]), (150, 1000))
        self.assertEqual(mapped.world_start, (10150, 20000))
        self.assertEqual(mapped.world_end, (10150, 21000))

    def test_linear_update_contract_accepts_waler_and_brace(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        rows = {"walers": walers, "struts": [], "braces": [brace]}

        waler = CadEventMapper.map_command(
            self.linear_update_event(
                "waler",
                "W1",
                start=(0, 100),
                end=(2000, 100),
            ),
            rows,
        )
        brace_mapped = CadEventMapper.map_command(
            self.linear_update_event(
                "brace",
                "B2",
                start=(250, 0),
                end=(350, 1000),
            ),
            rows,
        )

        self.assertEqual((waler.table_name, waler.row_index), ("walers", 0))
        self.assertEqual((brace_mapped.table_name, brace_mapped.row_index), ("braces", 0))

    def test_linear_update_contract_rejects_missing_target_and_forbidden_fields(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        rows = {"walers": walers, "struts": [], "braces": [brace]}
        missing_target = self.linear_update_event("waler", "W1")
        missing_target.pop("target_id")
        waler_positions = self.linear_update_event(
            "waler",
            "W1",
            BeamPositions="100",
        )
        brace_relation = self.linear_update_event(
            "brace",
            "B2",
            start=(250, 0),
            end=(350, 1000),
            FromWaler="W2",
        )

        with self.assertRaisesRegex(ValueError, "target_id"):
            CadEventMapper.map_command(missing_target, rows)
        with self.assertRaisesRegex(ValueError, "BeamPositions"):
            CadEventMapper.map_command(waler_positions, rows)
        with self.assertRaisesRegex(ValueError, "FromWaler"):
            CadEventMapper.map_command(brace_relation, rows)

    def test_update_target_must_exist_once_in_its_own_table(self):
        walers, _strut = self.project_geometry()
        missing = self.linear_update_event("waler", "W9")
        duplicate_braces = [self.brace_row(), copy.deepcopy(self.brace_row())]

        with self.assertRaisesRegex(ValueError, "W9.*walers"):
            CadEventMapper.map_command(
                missing,
                {"walers": walers, "struts": [], "braces": []},
            )
        with self.assertRaisesRegex(ValueError, "B2.*braces.*唯一"):
            CadEventMapper.map_command(
                self.linear_update_event(
                    "brace",
                    "B2",
                    start=(250, 0),
                    end=(350, 1000),
                ),
                {"walers": walers, "struts": [], "braces": duplicate_braces},
            )

    def test_waler_update_preserves_nongeometry_and_normalizes_pick_direction(self):
        walers, _strut = self.project_geometry()
        walers[0].update(material_spec="H400x400", Remark="keep me")
        rows = {"walers": walers, "struts": [], "braces": []}

        forward = CadEventMapper.map_command(
            self.linear_update_event(
                "waler",
                "W1",
                start=(100, 5000),
                end=(2100, 5000),
            ),
            rows,
        )
        reverse = CadEventMapper.map_command(
            self.linear_update_event(
                "waler",
                "W1",
                start=(2100, 5000),
                end=(100, 5000),
            ),
            rows,
        )

        self.assertEqual(
            tuple(forward.row[field] for field in ("StartX", "StartY", "EndX", "EndY")),
            (100, 5000, 2100, 5000),
        )
        self.assertEqual(forward.row, reverse.row)
        self.assertEqual(forward.row["WalerID"], "W1")
        self.assertEqual(forward.row["material_spec"], "H400x400")
        self.assertEqual(forward.row["Remark"], "keep me")

    def test_brace_update_preserves_relation_and_reverses_cad_pick(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()

        mapped = CadEventMapper.map_command(
            self.linear_update_event(
                "brace",
                "B2",
                start=(400, 1000),
                end=(250, 0),
            ),
            {"walers": walers, "struts": [], "braces": [brace]},
        )

        self.assertEqual((mapped.row["StartX"], mapped.row["StartY"]), (250, 0))
        self.assertEqual((mapped.row["EndX"], mapped.row["EndY"]), (400, 1000))
        self.assertEqual(mapped.row["BraceID"], "B2")
        self.assertEqual(
            (mapped.row["FromWaler"], mapped.row["ToWaler"]),
            ("W1", "W2"),
        )
        self.assertEqual(mapped.world_start, (250, 0))
        self.assertEqual(mapped.world_end, (400, 1000))

    def test_brace_update_rejects_geometry_outside_original_waler_relation(self):
        walers, _strut = self.project_geometry()

        with self.assertRaisesRegex(
            ValueError,
            "新斜撐幾何無法維持原 FromWaler / ToWaler 關係",
        ):
            CadEventMapper.map_command(
                self.linear_update_event(
                    "brace",
                    "B2",
                    start=(5000, 3000),
                    end=(5000, 4000),
                ),
                {"walers": walers, "struts": [], "braces": [self.brace_row()]},
            )

    def test_waler_and_brace_update_reject_lines_below_geometry_minimum(self):
        walers, _strut = self.project_geometry()
        rows = {"walers": walers, "struts": [], "braces": [self.brace_row()]}

        for event in (
            self.linear_update_event("waler", "W1", start=(0, 0), end=(50, 0)),
            self.linear_update_event("brace", "B2", start=(0, 0), end=(50, 0)),
        ):
            with self.subTest(member_type=event["type"]), self.assertRaisesRegex(
                ValueError,
                "100 mm",
            ):
                CadEventMapper.map_command(event, rows)

    def test_waler_and_brace_update_share_wcs_to_local_conversion(self):
        walers, _strut = self.project_geometry()
        rows = {"walers": walers, "struts": [], "braces": [self.brace_row()]}
        coordinate = CoordinateSystem("local", 10000, 20000, "test")

        waler = CadEventMapper.map_command(
            self.linear_update_event(
                "waler",
                "W1",
                start=(10100, 20200),
                end=(12100, 20200),
            ),
            rows,
            coordinate_system=coordinate,
        )
        brace = CadEventMapper.map_command(
            self.linear_update_event(
                "brace",
                "B2",
                start=(10400, 21000),
                end=(10250, 20000),
            ),
            rows,
            coordinate_system=coordinate,
        )

        self.assertEqual(
            tuple(waler.row[field] for field in ("StartX", "StartY", "EndX", "EndY")),
            (100, 200, 2100, 200),
        )
        self.assertEqual(
            tuple(brace.row[field] for field in ("StartX", "StartY", "EndX", "EndY")),
            (250, 0, 400, 1000),
        )
        self.assertEqual(brace.world_start, (10250, 20000))
        self.assertEqual(brace.world_end, (10400, 21000))

    def test_update_rejects_geometry_that_matches_neither_original_waler_direction(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        self.write_event(
            self.update_event(start=(5000, 3000), end=(5000, 4000))
        )

        self.assertFalse(app.read_cad_event())

        self.assertTrue(self.event_path.is_file())
        self.assertEqual(len(app.struts), 1)
        self.assertEqual(app.struts[0]["StartX"], 100)
        self.assertIsNotNone(app.cad_last_error)
        self.assertIn("SUPCLEAR", app.cad_last_error)

    def test_cancel_event_clears_pending_file_without_changing_project(self):
        app = self.main_app_for_cad_import()
        original_walers = copy.deepcopy(app.walers)
        original_results = copy.deepcopy(app.result_items)
        event = {
            "event_id": "cancel-rejected-update",
            "type": "control",
            "operation": "cancel",
            "coordinate_space": "WCS",
            "data": {},
        }
        self.write_event(event)

        self.assertTrue(app.read_cad_event())

        self.assertFalse(self.event_path.exists())
        self.assertEqual(app.walers, original_walers)
        self.assertEqual(app.result_items, original_results)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.preview_update_count, 0)
        self.assertEqual(app.cad_last_event, event)
        self.assertIn("Project 資料未變更", app.cad_import_status)

    def test_update_replaces_strut_in_place_and_syncs_unique_dxf_binding(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        original_state = self.dxf_state()
        source_geometry = copy.deepcopy(original_state["source_geometry"])
        original_handles = copy.deepcopy(
            original_state["converted"]["struts"][0]["source_handles"]
        )
        app.dxf_last_import_debug = original_state
        self.write_event(
            self.update_event(
                start=(200, 0),
                end=(200, 1000),
                beams="200,800",
                columns="400",
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(len(app.struts), 1)
        updated = app.struts[0]
        self.assertEqual(updated["StrutID"], "S5")
        self.assertEqual(updated["material_spec"], "H400x400")
        self.assertEqual(updated["Zoning"], "Z9")
        self.assertEqual(updated["TargetJackRegion"], 3)
        self.assertEqual(updated["SharedLayoutGroup"], "G1")
        self.assertEqual((updated["FromWaler"], updated["ToWaler"]), ("W1", "W2"))
        self.assertEqual((updated["StartX"], updated["EndX"]), (200, 200))
        self.assertEqual(updated["BeamPositions"], "200,800")
        self.assertEqual(updated["ColumnPositions"], "400")
        self.assertEqual(updated["AssociatedColumnIDs"], "")
        self.assertEqual(updated["AssociatedBeamIDs"], "")
        for field in SupportInputApp.STRUT_BRACE_LENGTH_FIELDS:
            self.assertEqual(updated[field[0]], 0)
        binding = app.dxf_last_import_debug["converted"]["struts"][0]
        self.assertEqual(binding["start"], [200.0, 0.0])
        self.assertEqual(binding["world_start"], [200.0, 0.0])
        self.assertEqual(binding["project_id"], "S5")
        self.assertEqual(binding["cad_event_id"], "update-s5")
        self.assertEqual(binding["selection_source"], "cad_manual")
        self.assertEqual(binding["source_handles"], original_handles)
        self.assertEqual(binding["source_layer"], "STRUT_LAYER")
        self.assertEqual(
            app.dxf_last_import_debug["source_geometry"],
            source_geometry,
        )
        self.assertFalse(app._dxf_binding_is_stale())
        self.assertEqual(app.result_items, {})
        self.assertIsNone(app.project_result)
        self.assertIsNone(app.last_calculated_time)
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})
        self.assertTrue(app.project_dirty)
        self.assertEqual(app.preview_update_count, 1)
        self.assertEqual(app.selected_rows, [("struts", 0)])
        self.assertIn("DXF 工程線已同步", app.cad_import_status)
        self.assertIn("柱/托梁關聯 ID 已清除", app.cad_import_status)
        self.assertIn("角撐長度已清除", app.cad_import_status)

    def test_local_project_update_keeps_project_and_world_binding_coordinates(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.dxf_last_import_debug = self.dxf_state(local=True)
        self.write_event(
            self.update_event(
                start=(10160, 20000),
                end=(10160, 21000),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(app.struts[0]["StartX"], 160)
        self.assertEqual(app.struts[0]["EndX"], 160)
        binding = app.dxf_last_import_debug["converted"]["struts"][0]
        self.assertEqual(binding["start"], [160.0, 0.0])
        self.assertEqual(binding["local_start"], [160.0, 0.0])
        self.assertEqual(binding["world_start"], [10160.0, 20000.0])
        self.assertEqual(binding["world_end"], [10160.0, 21000.0])
        self.assertFalse(app._dxf_binding_is_stale())

    def test_station_only_update_preserves_corner_brace_lengths(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.dxf_last_import_debug = self.dxf_state()
        self.write_event(
            self.update_event(beams="200,800", columns="400")
        )

        self.assertTrue(app.read_cad_event())

        updated = app.struts[0]
        self.assertEqual(updated["FromBraceToWalerStartLen"], 100)
        self.assertEqual(updated["FromBraceToWalerEndLen"], 200)
        self.assertEqual(updated["ToBraceToWalerStartLen"], 300)
        self.assertEqual(updated["ToBraceToWalerEndLen"], 400)
        self.assertNotIn("角撐長度已清除", app.cad_import_status)

    def test_ambiguous_binding_still_updates_project_and_marks_dxf_stale(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.dxf_last_import_debug = self.dxf_state(duplicate=True)
        original_world_lines = copy.deepcopy(
            app.dxf_last_import_debug["converted"]["struts"]
        )
        self.write_event(
            self.update_event(start=(250, 0), end=(250, 1000))
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(len(app.struts), 1)
        self.assertEqual(app.struts[0]["StartX"], 250)
        self.assertTrue(app._dxf_binding_is_stale())
        self.assertEqual(
            app.dxf_last_import_debug["converted"]["struts"],
            original_world_lines,
        )
        self.assertIn("DXF 圖面定位需重新確認", app.cad_import_status)

    def test_waler_update_commits_without_cascade_and_validation_reports_relations(self):
        walers, strut = self.project_geometry()
        walers[0].update(material_spec="H400x400", Remark="reviewed")
        brace = self.brace_row()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.braces = [brace]
        app.dxf_last_import_debug = self.dxf_state()
        old_struts = copy.deepcopy(app.struts)
        old_braces = copy.deepcopy(app.braces)
        self.write_event(
            self.linear_update_event(
                "waler",
                "W1",
                start=(0, 200),
                end=(2000, 200),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(
            tuple(
                app.walers[0][field]
                for field in ("StartX", "StartY", "EndX", "EndY")
            ),
            (0, 200, 2000, 200),
        )
        self.assertEqual(app.walers[0]["material_spec"], "H400x400")
        self.assertEqual(app.walers[0]["Remark"], "reviewed")
        self.assertEqual(app.struts, old_struts)
        self.assertEqual(app.braces, old_braces)
        self.assertTrue(app._dxf_binding_is_stale())
        self.assertEqual(app.result_items, {})
        self.assertIsNone(app.project_result)
        relation_tables = {
            issue.table for issue in app.last_cad_validation_report.errors
        }
        self.assertIn("struts", relation_tables)
        self.assertIn("braces", relation_tables)
        self.assertIn("Validation 發現", app.cad_import_status)

    def test_waler_equivalent_reverse_pick_is_a_noop(self):
        walers, _strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        original_state = self.dxf_state()
        app.dxf_last_import_debug = original_state
        original_results = copy.deepcopy(app.result_items)
        self.write_event(
            self.linear_update_event(
                "waler",
                "W1",
                start=(2000, 0),
                end=(0, 0),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertFalse(self.event_path.exists())
        self.assertEqual(app.result_items, original_results)
        self.assertFalse(app.project_dirty)
        self.assertEqual(app.preview_update_count, 0)
        self.assertIs(app.dxf_last_import_debug, original_state)
        self.assertFalse(app._dxf_binding_is_stale())
        self.assertIn("幾何未變更", app.cad_import_status)

    def test_brace_update_syncs_one_safe_dxf_binding(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        app = self.main_app_for_cad_import(walers=walers)
        app.braces = [brace]
        app.dxf_last_import_debug = self.dxf_state(
            include_strut=False,
            brace=brace,
        )
        source_handles = copy.deepcopy(
            app.dxf_last_import_debug["converted"]["braces"][0]["source_handles"]
        )
        self.write_event(
            self.linear_update_event(
                "brace",
                "B2",
                start=(250, 0),
                end=(350, 1000),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(
            tuple(
                app.braces[0][field]
                for field in ("StartX", "StartY", "EndX", "EndY")
            ),
            (250, 0, 350, 1000),
        )
        self.assertEqual(
            (app.braces[0]["FromWaler"], app.braces[0]["ToWaler"]),
            ("W1", "W2"),
        )
        binding = app.dxf_last_import_debug["converted"]["braces"][0]
        self.assertEqual(binding["start"], [250.0, 0.0])
        self.assertEqual(binding["end"], [350.0, 1000.0])
        self.assertEqual(binding["project_id"], "B2")
        self.assertEqual(binding["selection_source"], "cad_manual")
        self.assertEqual(binding["source_handles"], source_handles)
        self.assertFalse(app._dxf_binding_is_stale())
        self.assertEqual(app.result_items, {})
        self.assertIn("DXF 工程線已同步", app.cad_import_status)
        self.assertTrue(app.last_cad_validation_report.valid)

    def test_ambiguous_brace_binding_marks_stale_without_rolling_back_project(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        app = self.main_app_for_cad_import(walers=walers)
        app.braces = [brace]
        app.dxf_last_import_debug = self.dxf_state(
            include_strut=False,
            brace=brace,
            duplicate_brace=True,
        )
        old_bindings = copy.deepcopy(
            app.dxf_last_import_debug["converted"]["braces"]
        )
        self.write_event(
            self.linear_update_event(
                "brace",
                "B2",
                start=(260, 0),
                end=(360, 1000),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(app.braces[0]["StartX"], 260)
        self.assertTrue(app._dxf_binding_is_stale())
        self.assertEqual(
            app.dxf_last_import_debug["converted"]["braces"],
            old_bindings,
        )

    def test_existing_stale_state_is_not_fake_synced_by_brace_update(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        app = self.main_app_for_cad_import(walers=walers)
        app.braces = [brace]
        app.dxf_last_import_debug = self.dxf_state(
            include_strut=False,
            brace=brace,
        )
        app.dxf_last_import_debug[app.DXF_BINDING_STALE_KEY] = True
        old_binding = copy.deepcopy(
            app.dxf_last_import_debug["converted"]["braces"][0]
        )
        self.write_event(
            self.linear_update_event(
                "brace",
                "B2",
                start=(270, 0),
                end=(370, 1000),
            )
        )

        self.assertTrue(app.read_cad_event())

        self.assertEqual(app.braces[0]["StartX"], 270)
        self.assertTrue(app._dxf_binding_is_stale())
        self.assertEqual(
            app.dxf_last_import_debug["converted"]["braces"][0],
            old_binding,
        )

    def test_invalid_brace_relation_keeps_event_project_result_and_dxf_state(self):
        walers, _strut = self.project_geometry()
        brace = self.brace_row()
        app = self.main_app_for_cad_import(walers=walers)
        app.braces = [brace]
        app.dxf_last_import_debug = self.dxf_state(
            include_strut=False,
            brace=brace,
        )
        old_row = copy.deepcopy(app.braces[0])
        old_state = copy.deepcopy(app.dxf_last_import_debug)
        old_results = copy.deepcopy(app.result_items)
        self.write_event(
            self.linear_update_event(
                "brace",
                "B2",
                start=(5000, 3000),
                end=(5000, 4000),
            )
        )

        self.assertFalse(app.read_cad_event())

        self.assertTrue(self.event_path.is_file())
        self.assertEqual(app.braces[0], old_row)
        self.assertEqual(app.dxf_last_import_debug, old_state)
        self.assertEqual(app.result_items, old_results)
        self.assertIn("新斜撐幾何無法維持", app.cad_last_error)

    def test_waler_and_brace_ack_failure_use_generic_row_rollback(self):
        walers, _strut = self.project_geometry()
        for member_type, table_name, target_id, row, event in (
            (
                "waler",
                "walers",
                "W1",
                walers[0],
                self.linear_update_event(
                    "waler",
                    "W1",
                    start=(0, 100),
                    end=(2000, 100),
                ),
            ),
            (
                "brace",
                "braces",
                "B2",
                self.brace_row(),
                self.linear_update_event(
                    "brace",
                    "B2",
                    start=(250, 0),
                    end=(350, 1000),
                ),
            ),
        ):
            with self.subTest(member_type=member_type):
                app = self.main_app_for_cad_import(walers=walers)
                setattr(app, table_name, [row])
                if table_name == "braces":
                    app.dxf_last_import_debug = self.dxf_state(
                        include_strut=False,
                        brace=row,
                    )
                else:
                    app.dxf_last_import_debug = self.dxf_state()
                original_row = copy.deepcopy(getattr(app, table_name)[0])
                original_state = copy.deepcopy(app.dxf_last_import_debug)
                original_results = copy.deepcopy(app.result_items)
                app.cad_event_watcher = Mock()
                app.cad_event_watcher.acknowledge.side_effect = OSError("ack failed")

                with self.assertRaisesRegex(OSError, "ack failed"):
                    app._apply_cad_event(event)

                self.assertEqual(getattr(app, table_name), [original_row])
                self.assertEqual(app.dxf_last_import_debug, original_state)
                self.assertEqual(app.result_items, original_results)
                self.assertEqual(app.preview_update_count, 0)

    def test_project_replace_failure_does_not_ack_or_change_adjacent_state(self):
        walers, _strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        original_walers = copy.deepcopy(app.walers)
        original_results = copy.deepcopy(app.result_items)
        original_state = self.dxf_state()
        app.dxf_last_import_debug = original_state
        app.cad_event_watcher = Mock()
        project_data = app._ensure_project_data()

        with patch.object(
            project_data,
            "replace_row",
            side_effect=ValueError("replace failed"),
        ), self.assertRaisesRegex(ValueError, "replace failed"):
            app._apply_cad_event(
                self.linear_update_event(
                    "waler",
                    "W1",
                    start=(0, 100),
                    end=(2000, 100),
                )
            )

        app.cad_event_watcher.acknowledge.assert_not_called()
        self.assertEqual(app.walers, original_walers)
        self.assertEqual(app.result_items, original_results)
        self.assertIs(app.dxf_last_import_debug, original_state)

    def test_ack_failure_rolls_back_project_row_and_dxf_state(self):
        walers, strut = self.project_geometry()
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.dxf_last_import_debug = self.dxf_state()
        original_row = copy.deepcopy(app.struts[0])
        original_state = copy.deepcopy(app.dxf_last_import_debug)
        app.cad_event_watcher = Mock()
        app.cad_event_watcher.acknowledge.side_effect = OSError("ack failed")

        with self.assertRaisesRegex(OSError, "ack failed"):
            app._apply_cad_event(
                self.update_event(start=(200, 0), end=(200, 1000))
            )

        self.assertEqual(app.struts, [original_row])
        self.assertEqual(app.dxf_last_import_debug, original_state)
        self.assertEqual(app.preview_update_count, 0)

    def test_dxf_import_dialog_does_not_consume_update_event(self):
        event = self.update_event()
        self.write_event(event)
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.world_result = object()
        dialog._selected_member = lambda: SimpleNamespace(id="S5")
        dialog._member_role = lambda _member: ("strut", "支撐")
        dialog.cad_temp_status_var = Mock()
        dialog.cad_event_watcher = TempEventWatcher(self.event_path)

        with patch("tkinter.messagebox.showerror") as show_error:
            dialog._read_cad_engineering_line()
            dialog._read_cad_engineering_line()

        self.assertTrue(self.event_path.is_file())
        self.assertIsNotNone(dialog.cad_event_watcher.check_new_event())
        show_error.assert_not_called()
        self.assertIn(
            "事件已保留",
            dialog.cad_temp_status_var.set.call_args.args[0],
        )

    def test_dxf_import_dialog_leaves_waler_and_brace_updates_for_main(self):
        for member_type, target_id, command_name in (
            ("waler", "W1", "UPDWALER"),
            ("brace", "B2", "UPDBRACE"),
        ):
            with self.subTest(member_type=member_type):
                event = self.linear_update_event(
                    member_type,
                    target_id,
                    start=(0, 0),
                    end=(1000, 0),
                )
                self.write_event(event)
                dialog = DXFImportDialog.__new__(DXFImportDialog)
                dialog.world_result = object()
                dialog._selected_member = lambda: SimpleNamespace(id=target_id)
                dialog._member_role = lambda _member: (member_type, member_type)
                dialog.cad_temp_status_var = Mock()
                dialog.cad_event_watcher = TempEventWatcher(self.event_path)

                with patch("tkinter.messagebox.showerror") as show_error:
                    dialog._read_cad_engineering_line()

                self.assertTrue(self.event_path.is_file())
                show_error.assert_not_called()
                self.assertIn(
                    command_name,
                    dialog.cad_temp_status_var.set.call_args.args[0],
                )

    def test_dxf_import_dialog_does_not_consume_cancel_event(self):
        event = {
            "event_id": "cancel-from-lsp",
            "type": "control",
            "operation": "cancel",
            "coordinate_space": "WCS",
            "data": {},
        }
        self.write_event(event)
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.world_result = object()
        dialog._selected_member = lambda: SimpleNamespace(id="S5")
        dialog._member_role = lambda _member: ("strut", "支撐")
        dialog.cad_temp_status_var = Mock()
        dialog.cad_event_watcher = TempEventWatcher(self.event_path)

        with patch("tkinter.messagebox.showerror") as show_error:
            dialog._read_cad_engineering_line()

        self.assertTrue(self.event_path.is_file())
        self.assertIsNotNone(dialog.cad_event_watcher.check_new_event())
        show_error.assert_not_called()
        self.assertIn(
            "SUPCLEAR 事件已保留",
            dialog.cad_temp_status_var.set.call_args.args[0],
        )

    def test_invalid_cad_event_remains_pending_and_does_not_change_main_data(self):
        app = self.main_app_for_cad_import()
        self.event_path.write_text(
            json.dumps({
                "event_id": "bad-event",
                "type": "circle",
                "operation": "add",
                "coordinate_space": "WCS",
                "data": {"StartX": 1},
            }),
            encoding="utf-8",
        )

        self.assertFalse(app.read_cad_event())

        self.assertTrue(self.event_path.exists())
        self.assertEqual(len(app.walers), 1)
        self.assertEqual(app.walers[0]["WalerID"], "W2")
        self.assertEqual(app.cad_import_status, "CAD 事件匯入失敗")
        self.assertIsNotNone(app.cad_last_error)

    def test_cad_events_export_and_load_in_main(self):
        app = self.main_app_for_cad_import(walers=[])
        app.project_cases_dir = self.temp_path
        app.project_result = None
        app.last_calculated_time = None
        app.current_project_path = None
        app._collect_visible_material_usage = lambda: {}
        app._collect_inventory_quantities = lambda: {}
        self.write_event({
            "event_id": "waler-1",
            "type": "waler",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {"StartX": 0, "StartY": 0, "EndX": 1000, "EndY": 0},
        })
        self.assertTrue(app.read_cad_event())
        self.write_event({
            "event_id": "waler-2",
            "type": "waler",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {"StartX": 0, "StartY": 1000, "EndX": 1000, "EndY": 1000},
        })
        self.assertTrue(app.read_cad_event())
        self.write_event({
            "event_id": "support-1",
            "type": "support",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {
                "FromWaler": "W1",
                "ToWaler": "W2",
                "StartX": 100,
                "StartY": 0,
                "EndX": 100,
                "EndY": 1000,
                "BeamPositions": "250,750",
                "ColumnPositions": "500",
                "Zoning": "Z1",
            },
        })
        self.assertTrue(app.read_cad_event())
        self.assertEqual(app.struts[-1]["TargetJackRegion"], 2)
        self.write_event({
            "event_id": "brace-1",
            "type": "brace",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {
                "FromWaler": "W1",
                "ToWaler": "W2",
                "StartX": 0,
                "StartY": 0,
                "EndX": 100,
                "EndY": 100,
            },
        })
        self.assertTrue(app.read_cad_event())
        app.dxf_last_import_debug = {
            "layer_classification": {
                "FRAME_A": "waler",
                "SUPPORT_A": "strut",
            },
            "converted": {
                "walers": [{"id": "W1", "selection_source": "manual"}],
            },
        }

        output_path = app.save_project_case("cad-e2e")

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(
            set(payload["input_data"]),
            {
                "walers",
                "struts",
                "braces",
                "inventory",
                "material_specs",
            },
        )
        self.assertIsNone(payload["result"])
        self.assertNotIn("supports", payload)
        self.assertNotIn("supports", payload["input_data"])
        self.assertEqual(
            payload["dxf_import_state"]["layer_classification"]["FRAME_A"],
            "waler",
        )

        app = self.load_with_solver("cad-e2e")
        self.assertEqual(len(app.walers), 2)
        self.assertEqual(len(app.struts), 1)
        self.assertEqual(len(app.braces), 1)
        self.assertEqual(app.struts[0]["StrutID"], "S1")
        self.assertEqual(app.struts[0]["BeamPositions"], "250,750")
        self.assertEqual(app.struts[0]["ColumnPositions"], "500")
        self.assertEqual(app.struts[0]["TargetJackRegion"], 2)
        self.assertNotIn("Type", app.braces[0])
        self.assertEqual(
            app.dxf_last_import_debug["converted"]["walers"][0][
                "selection_source"
            ],
            "manual",
        )

    def test_updated_strut_survives_project_save_and_reload(self):
        walers, strut = self.project_geometry()
        strut["SharedLayoutGroup"] = ""
        app = self.main_app_for_cad_import(walers=walers)
        app.struts = [strut]
        app.project_cases_dir = self.temp_path
        app.current_project_path = None
        app._collect_visible_material_usage = lambda: {}
        app._collect_inventory_quantities = lambda: {}
        self.write_event(
            self.update_event(
                start=(180, 0),
                end=(180, 1000),
                beams="150,850",
                columns="450",
            )
        )

        self.assertTrue(app.read_cad_event())
        app.save_project_case("updated-strut")
        restored = self.load_with_solver("updated-strut")

        self.assertEqual(len(restored.struts), 1)
        self.assertEqual(restored.struts[0]["StrutID"], "S5")
        self.assertEqual(restored.struts[0]["StartX"], 180)
        self.assertEqual(restored.struts[0]["EndX"], 180)
        self.assertEqual(restored.struts[0]["BeamPositions"], "150,850")
        self.assertEqual(restored.struts[0]["ColumnPositions"], "450")
        self.assertEqual(restored.struts[0]["material_spec"], "H400x400")

    def test_acknowledged_event_is_not_replayed_after_restart(self):
        event = {
            "event_id": "waler-once",
            "type": "waler",
            "operation": "add",
            "coordinate_space": "WCS",
            "data": {"StartX": 0, "StartY": 0, "EndX": 1, "EndY": 1},
        }
        self.write_event(event)
        loaded_event = self.watcher.check_new_event()
        self.assertIsNotNone(loaded_event)
        self.watcher.acknowledge(loaded_event)
        restarted_watcher = TempEventWatcher(self.event_path)
        self.assertIsNone(restarted_watcher.check_new_event())

    def test_main_rejects_legacy_case_until_offline_upgrade(self):
        payload = {
            "schema_version": 1,
            "case_name": "legacy",
            "data": {
                "walers": [],
                "struts": [{
                    "StrutID": "S1",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 1000,
                    "EndY": 0,
                    "Beam1": 250,
                    "Beam2": "",
                    "Column1": "",
                    "Column2": "",
                }],
                "braces": [{
                    "BraceID": "B1",
                    "Type": "KneeBrace",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 1,
                    "EndY": 1,
                }],
            },
        }
        (self.temp_path / "legacy.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )
        with self.assertRaises(ProjectPersistenceError):
            self.load_with_solver("legacy")


if __name__ == "__main__":
    unittest.main()
