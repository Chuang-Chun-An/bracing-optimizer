import copy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from main import SupportInputApp
from bracing_optimizer.application.project_data import ProjectDataModel, TABLE_COLUMNS
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder
from bracing_optimizer.infrastructure.dxf_result_export import (
    DXFExportMode,
    ExportPiece,
    MemberExportPlan,
)
from bracing_optimizer.infrastructure.project_persistence import (
    DxfCompatibilityChecker,
    DxfStatus,
)


def confirmed_import_state():
    return {
        "source_path": "source.dxf",
        "coordinate_system": {"mode": "world"},
        "converted": {
            "walers": [
                {
                    "id": "W1",
                    "source_layer": "WALER",
                    "start": [0, 0],
                    "end": [3000, 0],
                }
            ],
            "struts": [
                {
                    "id": "S1",
                    "source_layer": "STRUT",
                    "start": [0, 0],
                    "end": [0, 3000],
                }
            ],
            "braces": [],
        },
    }


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeLabel:
    def __init__(self):
        self.options = {}

    def configure(self, **kwargs):
        self.options.update(kwargs)


class FakeEditor:
    def __init__(self, value):
        self.value = value
        self.destroyed = False

    def winfo_exists(self):
        return not self.destroyed

    def get(self):
        return self.value

    def destroy(self):
        self.destroyed = True


class FakeTree:
    def __init__(self, columns, children=(), selection=()):
        self.columns = tuple(columns)
        self.children = list(children)
        self.selected = tuple(selection)
        self.values = {}

    def __getitem__(self, key):
        if key == "columns":
            return self.columns
        raise KeyError(key)

    def get_children(self):
        return tuple(self.children)

    def delete(self, *row_ids):
        for row_id in row_ids:
            if row_id in self.children:
                self.children.remove(row_id)

    def insert(self, _parent, _position, *, iid, values):
        self.children.append(iid)
        self.values[(iid, "values")] = tuple(values)

    def set(self, row_id, column, value=None):
        if value is None:
            return self.values.get((row_id, column), "")
        self.values[(row_id, column)] = value

    def selection(self):
        return self.selected

    def selection_set(self, row_id):
        self.selected = (row_id,)

    def focus(self, _row_id):
        return None

    def see(self, _row_id):
        return None


class MainProjectEditingTests(unittest.TestCase):
    def make_app(self, *, with_dxf=True):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = object()
        app.project_data = ProjectDataModel(
            walers=[
                {
                    "WalerID": "W1",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 3000,
                    "EndY": 0,
                    "material_spec": "H350x350",
                }
            ],
            struts=[
                {
                    "StrutID": "S1",
                    "FromWaler": "W1",
                    "ToWaler": "",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 0,
                    "EndY": 3000,
                    "material_spec": "H350x350",
                    "BeamPositions": "",
                    "ColumnPositions": "",
                    "TargetJackRegion": 2,
                    "Zoning": "Z1",
                }
            ],
            braces=[],
        )
        app.dxf_last_import_debug = (
            confirmed_import_state() if with_dxf else None
        )
        app.dxf_compatibility_checker = DxfCompatibilityChecker()
        app.last_dxf_compatibility_report = None
        app.numeric_columns = {
            "walers": ["StartX", "StartY", "EndX", "EndY"],
            "struts": [
                "StartX",
                "StartY",
                "EndX",
                "EndY",
                "FromBraceToWalerStartLen",
                "FromBraceToWalerEndLen",
                "ToBraceToWalerStartLen",
                "ToBraceToWalerEndLen",
                "TargetJackRegion",
            ],
            "braces": ["StartX", "StartY", "EndX", "EndY"],
            "inventory": ["Length", "Qty"],
            "material_specs": [],
        }
        app.table_column_labels = {
            table_name: {column: column for column in columns}
            for table_name, columns in TABLE_COLUMNS.items()
        }
        app.table_tab_labels = {
            "walers": "圍令",
            "struts": "支撐",
            "braces": "斜撐",
        }
        app.treeviews = {
            "walers": FakeTree(TABLE_COLUMNS["walers"], ("walers_0",)),
            "struts": FakeTree(TABLE_COLUMNS["struts"], ("struts_0",)),
            "braces": FakeTree(TABLE_COLUMNS["braces"]),
        }
        app.editing_entry = None
        app.selected_strut_index = None
        app.selected_geometry_indices = {}
        app._load_strut_detail = lambda _index: None
        app._load_geometry_detail = lambda _table, _index: None
        app._update_strut_detail_length = lambda _row=None: None
        app._sync_preview_to_strut_selection = lambda _index: None
        app._sync_preview_to_geometry_selection = lambda *_args: None
        app._update_material_summary = lambda: None
        app._refresh_results_tree = lambda: None
        app.events = {"dirty": 0, "preview": 0, "solver": 0}

        def mark_dirty(_reason):
            app.events["dirty"] += 1
            app.project_dirty = True

        def update_preview(**_kwargs):
            app.events["preview"] += 1

        def invalidate_solver():
            app.events["solver"] += 1

        app._mark_project_dirty = mark_dirty
        app.update_preview = update_preview
        app._invalidate_solver_state_after_input_change = invalidate_solver
        return app

    @staticmethod
    def edit_strut_detail(app, column, value):
        app.selected_strut_index = 0
        app._loading_strut_detail = False
        app.strut_detail_vars = {column: FakeVariable(value)}
        app.strut_detail_status_var = FakeVariable()
        app.strut_detail_status_label = FakeLabel()
        app._commit_strut_detail_field(column)

    @staticmethod
    def edit_inline(app, table_name, column, value, index=0):
        tree = app.treeviews[table_name]
        editor = FakeEditor(value)
        app.editing_entry = editor
        app._finish_edit(
            tree,
            f"{table_name}_{index}",
            column,
            editor,
        )

    def test_unmodified_project_is_compatible_with_confirmed_dxf(self):
        app = self.make_app()

        compatible, report = app._check_dxf_export_compatibility(
            app.dxf_last_import_debug
        )

        self.assertTrue(compatible)
        self.assertEqual(report.status, DxfStatus.GEOMETRY_COMPATIBLE)

        app._visible_dxf_export_plans = lambda: (
            MemberExportPlan(
                "W1",
                "waler",
                (ExportPiece("steel", 3000),),
                result_id="W1-plan",
            ),
        )
        export_report = SimpleNamespace(
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_counts=(),
            layer_name_fallbacks=(),
            dxf_version="R2010",
            coordinate_units="mm",
            background_layer_count=0,
            background_segment_count=0,
            final_audit=SimpleNamespace(error_count=0, fix_count=0),
            actual_dimension_count=1,
            dimension_count=1,
            actual_jack_count=0,
            jack_count=0,
            project_geometry_count=2,
            result_waler_count=1,
            result_support_count=0,
            output_path="result.dxf",
            merge_guidance="",
        )
        with (
            patch(
                "main.filedialog.asksaveasfilename",
                return_value="result.dxf",
            ),
            patch(
                "main.export_results_to_dxf",
                return_value=export_report,
            ) as export_results,
            patch("main.messagebox.showinfo") as show_info,
        ):
            app._export_visible_results_to_dxf()

        export_results.assert_called_once()
        args = export_results.call_args.args
        self.assertIs(args[2], app.walers)
        self.assertIs(args[3], app.struts)
        self.assertIs(args[4], app.braces)
        self.assertEqual(DXFExportMode.SOURCE_BACKED, export_results.call_args.kwargs["export_mode"])
        self.assertEqual(2, show_info.call_count)
        self.assertIn("Source-backed", show_info.call_args_list[0].args[0])

    def test_only_binding_fields_are_classified_as_dxf_stale_changes(self):
        binding_fields = {
            "walers": ("WalerID", "StartX", "StartY", "EndX", "EndY"),
            "struts": (
                "StrutID",
                "FromWaler",
                "ToWaler",
                "StartX",
                "StartY",
                "EndX",
                "EndY",
            ),
            "braces": (
                "BraceID",
                "FromWaler",
                "ToWaler",
                "StartX",
                "StartY",
                "EndX",
                "EndY",
            ),
        }
        for table_name, fields in binding_fields.items():
            for field_name in fields:
                with self.subTest(table=table_name, field=field_name):
                    self.assertTrue(
                        SupportInputApp._project_field_affects_dxf_binding(
                            table_name,
                            field_name,
                        )
                    )
        for field_name in ("material_spec", "Zoning", "TargetJackRegion"):
            with self.subTest(field=field_name):
                self.assertFalse(
                    SupportInputApp._project_field_affects_dxf_binding(
                        "struts",
                        field_name,
                    )
                )

    def test_strut_coordinate_edit_marks_dxf_binding_stale(self):
        app = self.make_app()

        changed, value, error = app._commit_project_field_edit(
            "struts", 0, "StartX", "100"
        )

        self.assertTrue(changed)
        self.assertEqual(value, 100)
        self.assertEqual(error, "")
        self.assertTrue(app._dxf_binding_is_stale())

    def test_waler_endpoint_edit_marks_dxf_binding_stale(self):
        app = self.make_app()

        app._commit_project_field_edit("walers", 0, "EndX", "2500")

        self.assertTrue(app._dxf_binding_is_stale())

    def test_material_spec_edit_does_not_mark_geometry_stale(self):
        app = self.make_app()

        app._commit_project_field_edit(
            "struts", 0, "material_spec", "H400x400"
        )

        self.assertFalse(app._dxf_binding_is_stale())
        self.assertEqual(app.struts[0]["material_spec"], "H400x400")
        self.assertEqual(app.events["solver"], 1)

    def test_waler_steel_rc_transitions_clear_results_and_runtime_caches(self):
        app = self.make_app(with_dxf=False)
        app._invalidate_solver_state_after_input_change = (
            SupportInputApp._invalidate_solver_state_after_input_change.__get__(
                app,
                SupportInputApp,
            )
        )

        def seed_solver_state():
            app._project_results = ProjectResultModel(
                result_items={"W1-方案1": {"type": "waler", "result": {}}},
                persisted_payload={"best_solution": {}},
            )
            app.solver_memory = {"old": object()}
            app.support_candidate_cache = {"old": object()}

        seed_solver_state()
        changed, _value, error = app._commit_project_field_edit(
            "walers", 0, "material_spec", "RC"
        )

        self.assertTrue(changed)
        self.assertEqual(error, "")
        self.assertEqual(app.walers[0]["material_spec"], "RC")
        self.assertEqual(app.result_items, {})
        self.assertIsNone(app.project_result)
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})

        seed_solver_state()
        changed, _value, error = app._commit_project_field_edit(
            "walers", 0, "material_spec", "H350x350"
        )

        self.assertTrue(changed)
        self.assertEqual(error, "")
        self.assertEqual(app.walers[0]["material_spec"], "H350x350")
        self.assertEqual(app.result_items, {})
        self.assertIsNone(app.project_result)
        self.assertEqual(app.solver_memory, {})
        self.assertEqual(app.support_candidate_cache, {})

    def test_uncommitted_waler_material_edit_preserves_solver_state(self):
        app = self.make_app(with_dxf=False)
        original_results = {
            "W1-方案1": {"type": "waler", "result": {"waler_id": "W1"}}
        }
        app._project_results = ProjectResultModel(
            result_items=copy.deepcopy(original_results),
            persisted_payload={"best_solution": {}},
        )
        app.solver_memory = {"old": 1}
        app.support_candidate_cache = {"old": 2}
        app._invalidate_solver_state_after_input_change = (
            SupportInputApp._invalidate_solver_state_after_input_change.__get__(
                app,
                SupportInputApp,
            )
        )

        changed, _value, error = app._commit_project_field_edit(
            "walers", 0, "material_spec", "H350x350"
        )
        missing_changed, _missing_value, missing_error = (
            app._commit_project_field_edit(
                "walers", 99, "material_spec", "RC"
            )
        )

        self.assertFalse(changed)
        self.assertEqual(error, "")
        self.assertFalse(missing_changed)
        self.assertTrue(missing_error)
        self.assertEqual(app.result_items, original_results)
        self.assertEqual(app.solver_memory, {"old": 1})
        self.assertEqual(app.support_candidate_cache, {"old": 2})

    def test_main_allows_geometry_invalid_zoning_to_be_edited(self):
        app = self.make_app(with_dxf=False)
        app.struts.append({
            **app.struts[0],
            "StrutID": "S2",
            "StartY": 1000,
            "EndY": 4000,
        })

        changed, value, error = app._commit_project_field_edit(
            "struts", 1, "EndX", "1000"
        )

        self.assertTrue(changed)
        self.assertEqual(value, 1000)
        self.assertEqual(error, "")
        self.assertEqual(app.struts[1]["Zoning"], "Z1")
        self.assertEqual(app.events["dirty"], 1)
        self.assertEqual(app.events["solver"], 1)

    def test_solver_geometry_preflight_preserves_committed_result(self):
        app = self.make_app(with_dxf=False)
        app.project_data.replace_table("struts", [
            {
                **app.struts[0],
                "StrutID": "S1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 10000,
                "EndY": 0,
            },
            {
                **app.struts[0],
                "StrutID": "S2",
                "StartX": 0,
                "StartY": 1000,
                "EndX": 9900,
                "EndY": 2500,
            },
        ])
        committed = {"Z1": {"type": "support", "result": "old"}}
        app.result_items = committed.copy()
        messages = []
        app.validate_data = lambda: True
        app.show_result = messages.append
        app._ensure_solver_input_builders = lambda: (SupportInputBuilder(), None)

        selection = SimpleNamespace(open=lambda: "Z1")
        with (
            patch("main.ZoningSelectionDialog", return_value=selection),
            patch("main.SupportSolverDialog") as dialog,
        ):
            app._open_support_solver()

        dialog.assert_not_called()
        self.assertEqual(app.result_items, committed)
        self.assertTrue(any("Zoning 幾何驗證失敗" in message for message in messages))
        self.assertTrue(any("未進入 Phase 2" in message for message in messages))
        self.assertTrue(any("方向差" in message for message in messages))

    def test_stale_binding_does_not_block_current_project_export(self):
        app = self.make_app()
        app.dxf_asset_status_report = SimpleNamespace(can_export=False)
        app._commit_project_field_edit("struts", 0, "StartX", "500")
        app._visible_dxf_export_plans = lambda: (
            MemberExportPlan(
                "S1",
                "strut",
                (ExportPiece("steel", 3000),),
                result_id="S1-plan",
            ),
        )
        export_report = SimpleNamespace(
            export_mode=DXFExportMode.SOURCE_BACKED,
            background_counts=(),
            layer_name_fallbacks=(),
            dxf_version="R2018",
            coordinate_units="mm",
            background_layer_count=0,
            background_segment_count=0,
            project_geometry_count=2,
            final_audit=SimpleNamespace(error_count=0, fix_count=0),
            actual_dimension_count=1,
            dimension_count=1,
            actual_jack_count=0,
            jack_count=0,
            result_waler_count=0,
            result_support_count=1,
            output_path="result.dxf",
            merge_guidance="",
        )

        with (
            patch("main.messagebox.showwarning") as warning,
            patch("main.filedialog.asksaveasfilename", return_value="result.dxf"),
            patch(
                "main.export_results_to_dxf",
                return_value=export_report,
            ) as export_results,
            patch("main.messagebox.showinfo"),
        ):
            app._export_visible_results_to_dxf()

        warning.assert_not_called()
        export_results.assert_called_once()
        self.assertEqual(500, export_results.call_args.args[3][0]["StartX"])

    def test_manual_project_exports_in_result_only_mode(self):
        app = self.make_app(with_dxf=False)
        events = []
        app._visible_dxf_export_plans = lambda: (
            MemberExportPlan(
                "W1",
                "waler",
                (ExportPiece("steel", 3000),),
                result_id="W1-plan",
            ),
        )

        export_report = SimpleNamespace(
            export_mode=DXFExportMode.RESULT_ONLY,
            background_counts=(),
            layer_name_fallbacks=(),
            dxf_version="R2018",
            coordinate_units="mm",
            background_layer_count=0,
            background_segment_count=0,
            project_geometry_count=0,
            final_audit=SimpleNamespace(error_count=0, fix_count=0),
            actual_dimension_count=1,
            dimension_count=1,
            actual_jack_count=0,
            jack_count=0,
            result_waler_count=1,
            result_support_count=0,
            output_path="result.dxf",
            merge_guidance=(
                "本檔使用目前 Project 座標直接輸出，未對齊任何來源圖面。"
                "合併至其他圖面時需由使用者自行定位。"
            ),
        )

        with (
            patch("main.messagebox.showwarning") as warning,
            patch(
                "main.messagebox.showinfo",
                side_effect=lambda title, *_args, **_kwargs: events.append(
                    f"info:{title}"
                ),
            ) as show_info,
            patch("main.filedialog.asksaveasfilename", return_value="result.dxf"),
            patch(
                "main.export_results_to_dxf",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("export") or export_report
                ),
            ) as export_results,
        ):
            app._export_visible_results_to_dxf()

        warning.assert_not_called()
        export_results.assert_called_once()
        self.assertEqual(DXFExportMode.RESULT_ONLY, export_results.call_args.kwargs["export_mode"])
        self.assertEqual("world", export_results.call_args.args[5].mode)
        self.assertIn("Result-only", show_info.call_args_list[0].args[0])
        completion = show_info.call_args_list[-1].args[1]
        self.assertIn("使用 Project 座標直接輸出", completion)
        self.assertIn("未對齊任何來源圖面", completion)
        self.assertIn("需自行定位", completion)
        self.assertNotIn("背景：", completion)
        self.assertNotIn("Project 工程線", completion)
        self.assertLess(events.index("info:DXF 匯出模式：Result-only"), events.index("export"))

    def test_manual_project_cancel_preserves_state_and_skips_export(self):
        app = self.make_app(with_dxf=False)
        app.project_dirty = False
        app._visible_dxf_export_plans = lambda: (
            MemberExportPlan(
                "W1",
                "waler",
                (ExportPiece("steel", 3000),),
                result_id="W1-plan",
            ),
        )
        original_rows = copy.deepcopy(app.walers)

        with (
            patch("main.messagebox.showinfo") as show_info,
            patch("main.filedialog.asksaveasfilename", return_value=""),
            patch("main.export_results_to_dxf") as export_results,
        ):
            app._export_visible_results_to_dxf()

        self.assertIn("Result-only", show_info.call_args.args[0])
        export_results.assert_not_called()
        self.assertEqual(original_rows, app.walers)
        self.assertFalse(app.project_dirty)

    def test_missing_import_state_attribute_uses_result_only(self):
        app = self.make_app(with_dxf=False)
        del app.dxf_last_import_debug
        app._visible_dxf_export_plans = lambda: (
            MemberExportPlan(
                "W1",
                "waler",
                (ExportPiece("steel", 3000),),
                result_id="W1-plan",
            ),
        )

        with (
            patch("main.messagebox.showinfo"),
            patch("main.filedialog.asksaveasfilename", return_value=""),
            patch("main.export_results_to_dxf") as export_results,
        ):
            app._export_visible_results_to_dxf()

        export_results.assert_not_called()

    def test_empty_import_state_reports_coordinate_error_without_fallback(self):
        app = self.make_app(with_dxf=False)
        app.dxf_last_import_debug = {}

        with (
            patch("main.messagebox.showwarning") as warning,
            patch("main.filedialog.asksaveasfilename") as save_dialog,
            patch("main.export_results_to_dxf") as export_results,
        ):
            app._export_visible_results_to_dxf()

        warning.assert_called_once()
        self.assertIn("Project → World", warning.call_args.args[0])
        save_dialog.assert_not_called()
        export_results.assert_not_called()

    def test_no_visible_or_duplicate_results_stop_before_file_dialog(self):
        app = self.make_app(with_dxf=False)
        duplicate = MemberExportPlan(
            "W1",
            "waler",
            (ExportPiece("steel", 3000),),
            result_id="W1-plan",
        )
        for plans in ((), (duplicate, duplicate)):
            with self.subTest(plan_count=len(plans)):
                app._visible_dxf_export_plans = lambda plans=plans: plans
                with (
                    patch("main.messagebox.showinfo") as show_info,
                    patch("main.messagebox.showwarning") as show_warning,
                    patch("main.filedialog.asksaveasfilename") as save_dialog,
                    patch("main.export_results_to_dxf") as export_results,
                ):
                    app._export_visible_results_to_dxf()

                show_warning.assert_called_once()
                show_info.assert_not_called()
                save_dialog.assert_not_called()
                export_results.assert_not_called()

    def test_translated_same_length_strut_is_incompatible(self):
        app = self.make_app()
        app.struts[0].update(
            {"StartX": 500, "StartY": 0, "EndX": 500, "EndY": 3000}
        )

        compatible, report = app._check_dxf_export_compatibility(
            app.dxf_last_import_debug
        )

        self.assertFalse(compatible)
        self.assertEqual(report.status, DxfStatus.INCOMPATIBLE)
        self.assertTrue(any("S1" in item for item in report.incompatible_items))

    def test_detail_and_inline_coordinate_edit_share_parse_and_postprocess(self):
        detail_app = self.make_app(with_dxf=False)
        inline_app = self.make_app(with_dxf=False)

        self.edit_strut_detail(detail_app, "StartX", "125.50")
        self.edit_inline(inline_app, "struts", "StartX", "125.50")

        self.assertEqual(detail_app.struts[0]["StartX"], 125.5)
        self.assertEqual(inline_app.struts[0]["StartX"], 125.5)
        self.assertEqual(
            detail_app.events,
            {"dirty": 1, "preview": 1, "solver": 1},
        )
        self.assertEqual(inline_app.events, detail_app.events)

    def test_detail_and_inline_both_reject_illegal_number(self):
        detail_app = self.make_app(with_dxf=False)
        inline_app = self.make_app(with_dxf=False)

        self.edit_strut_detail(detail_app, "StartX", "not-a-number")
        with patch("main.messagebox.showwarning") as warning:
            self.edit_inline(
                inline_app,
                "struts",
                "StartX",
                "not-a-number",
            )

        self.assertEqual(detail_app.struts[0]["StartX"], 0)
        self.assertEqual(inline_app.struts[0]["StartX"], 0)
        self.assertIn("必須是數字", detail_app.strut_detail_status_var.value)
        warning.assert_called_once()
        self.assertEqual(detail_app.events, {"dirty": 0, "preview": 0, "solver": 0})
        self.assertEqual(inline_app.events, detail_app.events)

    def test_detail_and_inline_share_position_list_normalization(self):
        detail_app = self.make_app(with_dxf=False)
        inline_app = self.make_app(with_dxf=False)

        self.edit_strut_detail(
            detail_app,
            "BeamPositions",
            "100， 250.5",
        )
        self.edit_inline(
            inline_app,
            "struts",
            "BeamPositions",
            "100， 250.5",
        )

        self.assertEqual(detail_app.struts[0]["BeamPositions"], "100, 250.5")
        self.assertEqual(inline_app.struts[0]["BeamPositions"], "100, 250.5")

    def test_tree_preview_and_detail_reads_do_not_modify_strut_rows(self):
        app = self.make_app(with_dxf=False)
        row = app.struts[0]
        row.update(Beam1=100, Beam2=200, Column1=300, Column2=400)
        before = copy.deepcopy(row)
        app.strut_detail_empty_var = FakeVariable()
        app.strut_length_var = FakeVariable()
        app._set_strut_detail_enabled = lambda _enabled: None

        SupportInputApp._refresh_tree(app, "struts")
        SupportInputApp._refresh_tree(app, "struts")

        app._material_spec_options = lambda _usage: ()
        app.strut_detail_widgets = {
            name: FakeLabel()
            for name in ("material_spec", "FromWaler", "ToWaler")
        }
        app.strut_detail_vars = {
            "BeamPositions": FakeVariable(),
            "ColumnPositions": FakeVariable(),
        }
        app.strut_detail_empty_var = FakeVariable()
        app.strut_detail_status_var = FakeVariable()
        app.strut_detail_status_label = FakeLabel()
        app._set_strut_detail_enabled = lambda _enabled: None
        app._update_strut_detail_length = lambda _row=None: None
        SupportInputApp._load_strut_detail(app, 0)
        SupportInputApp._load_strut_detail(app, 0)
        self.assertEqual(row, before)

        app.project_data.replace_table("walers", [])
        row["StartX"] = ""
        before_preview = copy.deepcopy(row)
        app.ax = Mock()
        app.ax.get_xlim.return_value = (0, 1)
        app.ax.get_ylim.return_value = (0, 1)
        app.ax.get_legend_handles_labels.return_value = ([], [])
        app.canvas = Mock()
        app.result_items = {}
        app._cancel_preview_scroll_redraw = lambda: None
        app._end_preview_interaction = lambda **_kwargs: None
        app._draw_result_overlays = lambda: None
        app._draw_preview_selection_highlight = lambda: None
        SupportInputApp.update_preview(app)
        SupportInputApp.update_preview(app)

        self.assertEqual(row, before_preview)
        self.assertEqual(app.events["dirty"], 0)
        self.assertEqual(app.strut_detail_vars["BeamPositions"].get(), "")
        self.assertEqual(app.strut_detail_vars["ColumnPositions"].get(), "")

    def test_blank_row_can_still_be_completed_one_field_at_a_time(self):
        app = self.make_app(with_dxf=False)
        app.project_data = ProjectDataModel()
        app.current_table = "struts"
        app.table_columns = {"struts": list(TABLE_COLUMNS["struts"])}
        tree = FakeTree(TABLE_COLUMNS["struts"])
        app.treeviews = {"struts": tree}

        def refresh_tree(_table_name):
            tree.children = [
                f"struts_{index}" for index in range(len(app.struts))
            ]

        app._refresh_tree = refresh_tree
        app.add_row()
        self.edit_inline(app, "struts", "StrutID", "S1")
        self.edit_inline(app, "struts", "StartX", "100")

        self.assertEqual(len(app.struts), 1)
        self.assertEqual(app.struts[0]["StrutID"], "S1")
        self.assertEqual(app.struts[0]["StartX"], 100)
        self.assertEqual(app.struts[0]["EndX"], "")
        self.assertEqual(app.struts[0]["TargetJackRegion"], 2)

    def test_deleting_geometry_member_marks_binding_stale(self):
        app = self.make_app()
        app.current_table = "walers"
        app.treeviews["walers"].selected = ("walers_0",)
        app._refresh_tree = lambda _table_name: None

        app.delete_row()

        self.assertEqual(app.walers, [])
        self.assertTrue(app._dxf_binding_is_stale())


if __name__ == "__main__":
    unittest.main()
