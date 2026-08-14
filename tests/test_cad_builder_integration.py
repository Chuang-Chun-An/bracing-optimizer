import json
import tempfile
import unittest
from pathlib import Path

from cad_builder import (
    DEFAULT_TEMP_PATH,
    EVENT_FILE_NAME,
    CadEventMapper,
    CadEventReader,
    TABLE_SPECS,
    TempEventWatcher,
)
from main import SupportInputApp
from project_data import TABLE_COLUMNS, ProjectDataModel


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
        app.solver_memory = {"old-memory": {}}
        app.support_candidate_cache = {"old-candidate": {}}
        app.cad_event_mapper = CadEventMapper()
        app.cad_event_watcher = TempEventWatcher(self.event_path)
        app.cad_import_status = "waiting"
        app.cad_last_event = None
        app.cad_last_error = None
        app.table_columns = {
            "walers": ["WalerID"],
            "struts": ["StrutID"],
            "braces": ["BraceID"],
        }
        app.treeviews = {}
        app.refreshed_tables = []
        app.preview_update_count = 0
        app.result_refresh_count = 0
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
            "ADDSTRUT",
            "ADDBRACE",
            "SUPSTATUS",
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
        self.assertIn("(trans", lisp_source)
        self.assertIn("(defun cb:projection-distance", lisp_source)
        self.assertIn("(defun cb:round-integer", lisp_source)
        lisp_source.encode("ascii")
        self.assertIn('(getpoint (strcat "\\nPick "', lisp_source)
        self.assertIn('(cb:capture-simple "waler" "waler")', lisp_source)
        self.assertIn("Pick beam points? [Yes/No] <No>:", lisp_source)
        self.assertIn("Pick column points? [Yes/No] <No>:", lisp_source)
        self.assertIn("Selected point is outside strut range.", lisp_source)
        self.assertIn('(rtos (getvar "CDATE") 2 8)', lisp_source)
        self.assertNotIn("MILLISECS", lisp_source)
        self.assertNotIn("cb:pending-message", lisp_source)
        self.assertNotIn("(findfile", lisp_source)
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
            "ADDSTRUT": "strut",
            "ADDBRACE": "brace",
        }
        for command, event_type in expected_types.items():
            encoded_event = json.dumps(examples[command], ensure_ascii=False)
            parsed_event = json.loads(encoded_event)
            self.assertEqual(parsed_event["type"], event_type)
            self.assertIsInstance(parsed_event["event_id"], str)
            self.assertIsInstance(parsed_event["data"], dict)

    def test_strut_event_maps_new_position_fields_without_legacy_columns(self):
        event = {
            "event_id": "new-strut-fields",
            "type": "strut",
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

    def test_invalid_cad_event_remains_pending_and_does_not_change_main_data(self):
        app = self.main_app_for_cad_import()
        self.event_path.write_text(
            json.dumps({
                "event_id": "bad-event",
                "type": "circle",
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
            "data": {"StartX": 0, "StartY": 0, "EndX": 1000, "EndY": 0},
        })
        self.assertTrue(app.read_cad_event())
        self.write_event({
            "event_id": "waler-2",
            "type": "waler",
            "data": {"StartX": 0, "StartY": 1000, "EndX": 1000, "EndY": 1000},
        })
        self.assertTrue(app.read_cad_event())
        self.write_event({
            "event_id": "support-1",
            "type": "support",
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
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(
            set(payload["input_data"]),
            {"walers", "struts", "braces", "inventory", "material_specs"},
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

    def test_acknowledged_event_is_not_replayed_after_restart(self):
        event = {
            "event_id": "waler-once",
            "type": "waler",
            "data": {"StartX": 0, "StartY": 0, "EndX": 1, "EndY": 1},
        }
        self.write_event(event)
        loaded_event = self.watcher.check_new_event()
        self.assertIsNotNone(loaded_event)
        self.watcher.acknowledge(loaded_event)
        restarted_watcher = TempEventWatcher(self.event_path)
        self.assertIsNone(restarted_watcher.check_new_event())

    def test_main_migrates_legacy_case_fields(self):
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
        app = self.load_with_solver("legacy")
        strut = app.struts[0]
        self.assertEqual(strut["BeamPositions"], "250")
        self.assertEqual(strut.get("ColumnPositions", ""), "")
        self.assertEqual(strut["TargetJackRegion"], 2)
        self.assertNotIn("Beam1", strut)
        self.assertNotIn("Type", app.braces[0])


if __name__ == "__main__":
    unittest.main()
