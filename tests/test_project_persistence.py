import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ezdxf
from bracing_optimizer.algorithms import support

from main import SupportInputApp
from bracing_optimizer.algorithms.solver_search import SolverDiagnostics
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
    DxfStatus,
    MANAGED_DXF_RELATIVE_PATH,
    ProjectPersistenceError,
)


def create_dxf(path: Path, *, layer="STRUCTURE", offset=0.0, handle=None):
    document = ezdxf.new("R2018")
    document.layers.add(layer)
    attribs = {"layer": layer}
    if handle is not None:
        attribs["handle"] = handle
    document.modelspace().add_line(
        (offset, 0),
        (offset + 3000, 0),
        dxfattribs=attribs,
    )
    document.saveas(path)
    return path


def import_state(source: Path, *, handle="10", layer="STRUCTURE", offset=0.0):
    return {
        "source_path": str(source),
        "coordinate_system": {
            "mode": "world",
            "origin_x": 0.0,
            "origin_y": 0.0,
        },
        "layer_classification": {layer: "waler"},
        "converted": {
            "walers": [{
                "id": "W1",
                "source_handles": [handle],
                "source_layer": layer,
                "source_entity_types": ["LINE"],
                "start": [offset, 0.0],
                "end": [offset + 3000, 0.0],
                "world_start": [offset, 0.0],
                "world_end": [offset + 3000, 0.0],
                "local_start": [offset, 0.0],
                "local_end": [offset + 3000, 0.0],
                "selection_source": "manual",
            }],
            "struts": [],
            "braces": [],
        },
    }


def payload(state=None, *, result=None):
    return {
        "schema_version": 3,
        "project_information": {"project_name": "測試專案"},
        "input_data": {
            "walers": [{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 3000,
                "EndY": 0,
            }],
            "struts": [],
            "braces": [],
        },
        "dxf_import_state": copy.deepcopy(state),
        "dxf_asset": None,
        "result": result,
    }


class ProjectPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.external = create_dxf(self.root / "原始 圖面.dxf")
        self.project_path = self.root / "含中文 空格專案" / "project.json"
        self.manager = DxfAssetManager()
        self.source = self.manager.verified_source(
            self.external,
            DxfStatus.RUNTIME_READY,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def save(self, *, manager=None, source=None, existing_asset=None, state=None):
        return (manager or self.manager).save_project(
            self.project_path,
            payload(state or import_state(self.external)),
            active_source=self.source if source is None else source,
            existing_asset=existing_asset,
        )

    def test_runtime_import_does_not_create_a_permanent_managed_copy(self):
        report = self.manager.runtime_report(self.external)

        self.assertEqual(report.status, DxfStatus.RUNTIME_READY)
        self.assertFalse((self.root / "source" / "source.dxf").exists())
        self.assertFalse(self.project_path.exists())

    def test_first_save_creates_project_json_and_managed_dxf(self):
        result = self.save()
        managed = self.project_path.parent / "source" / "source.dxf"

        self.assertTrue(self.project_path.is_file())
        self.assertTrue(managed.is_file())
        self.assertTrue(result.copied_dxf)
        saved = json.loads(self.project_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["schema_version"], 3)
        self.assertEqual(
            saved["dxf_asset"]["relative_path"],
            MANAGED_DXF_RELATIVE_PATH,
        )
        self.assertEqual(saved["dxf_asset"]["original_file_name"], "原始 圖面.dxf")
        self.assertNotIn(str(self.project_path.parent), saved["dxf_asset"]["relative_path"])

    def test_relative_path_resolves_after_moving_the_project_folder(self):
        result = self.save()
        moved = self.root / "另一台電腦" / "搬移後專案"
        moved.parent.mkdir(parents=True)
        self.project_path.parent.rename(moved)
        moved_json = moved / "project.json"

        report = self.manager.inspect(
            moved_json,
            result.dxf_asset,
            import_state(self.external),
            repair=False,
        )

        self.assertEqual(report.status, DxfStatus.READY)
        self.assertEqual(report.active_source.path, moved / "source" / "source.dxf")

    def test_unchanged_second_save_does_not_copy_dxf_again(self):
        first = self.save()
        managed = self.project_path.parent / "source" / "source.dxf"
        original_mtime = managed.stat().st_mtime_ns

        second = self.save(existing_asset=first.dxf_asset)

        self.assertFalse(second.copied_dxf)
        self.assertEqual(managed.stat().st_mtime_ns, original_mtime)
        self.assertTrue(self.project_path.with_name("project.json.bak").is_file())

    def test_changed_runtime_source_updates_managed_copy_and_metadata(self):
        first = self.save()
        replacement = create_dxf(self.root / "另一份.dxf", offset=5000)
        replacement_source = self.manager.verified_source(
            replacement,
            DxfStatus.RUNTIME_READY,
        )

        second = self.manager.save_project(
            self.project_path,
            payload(import_state(replacement, offset=5000)),
            active_source=replacement_source,
            existing_asset=first.dxf_asset,
        )

        self.assertTrue(second.copied_dxf)
        self.assertNotEqual(first.dxf_asset["sha256"], second.dxf_asset["sha256"])
        self.assertEqual(second.dxf_asset["original_file_name"], "另一份.dxf")

    def test_save_as_owns_an_independent_managed_copy(self):
        first = self.save()
        second_path = self.root / "另存專案" / "project.json"

        second = self.manager.save_project(
            second_path,
            payload(import_state(self.external)),
            active_source=self.manager.verified_source(
                self.project_path.parent / "source" / "source.dxf",
                DxfStatus.READY,
                original_path=self.external,
            ),
            existing_asset=first.dxf_asset,
        )

        self.assertTrue(second.copied_dxf)
        first_dxf = self.project_path.parent / "source" / "source.dxf"
        second_dxf = second_path.parent / "source" / "source.dxf"
        self.assertNotEqual(first_dxf, second_dxf)
        self.assertEqual(first_dxf.read_bytes(), second_dxf.read_bytes())

    def test_deleted_external_source_does_not_affect_ready_managed_copy(self):
        first = self.save()
        self.external.unlink()

        report = self.manager.inspect(
            self.project_path,
            first.dxf_asset,
            import_state(self.external),
            repair=False,
        )

        self.assertEqual(report.status, DxfStatus.READY)
        self.assertTrue(report.can_export)

    def test_missing_managed_copy_repairs_from_identical_original(self):
        first = self.save()
        managed = self.project_path.parent / "source" / "source.dxf"
        managed.unlink()

        report = self.manager.inspect(
            self.project_path,
            first.dxf_asset,
            import_state(self.external),
            repair=True,
        )

        self.assertEqual(report.status, DxfStatus.READY)
        self.assertTrue(report.repaired)
        self.assertTrue(managed.is_file())

    def test_modified_original_is_not_used_to_replace_a_missing_copy(self):
        first = self.save()
        managed = self.project_path.parent / "source" / "source.dxf"
        managed.unlink()
        create_dxf(self.external, offset=7000)

        report = self.manager.inspect(
            self.project_path,
            first.dxf_asset,
            import_state(self.external),
            repair=True,
        )

        self.assertEqual(report.status, DxfStatus.SOURCE_MODIFIED)
        self.assertFalse(report.can_export)
        self.assertFalse(managed.exists())

    def test_managed_copy_hash_mismatch_blocks_export(self):
        first = self.save()
        managed = self.project_path.parent / "source" / "source.dxf"
        create_dxf(managed, offset=9000)

        report = self.manager.inspect(
            self.project_path,
            first.dxf_asset,
            import_state(self.external),
            repair=False,
        )

        self.assertEqual(report.status, DxfStatus.MANAGED_COPY_MODIFIED)
        self.assertFalse(report.can_export)

    def test_manual_project_saves_without_a_dxf_asset(self):
        result = self.manager.save_project(
            self.project_path,
            payload(None),
            active_source=None,
            existing_asset=None,
        )

        saved = json.loads(self.project_path.read_text(encoding="utf-8"))
        self.assertIsNone(result.dxf_asset)
        self.assertIsNone(saved["dxf_asset"])
        self.assertFalse((self.project_path.parent / "source" / "source.dxf").exists())

    def test_long_unicode_project_path_saves_and_opens(self):
        long_path = (
            self.root
            / ("很長的專案資料夾 " + "甲" * 40)
            / ("第二層 " + "乙" * 40)
            / "project.json"
        )

        result = self.manager.save_project(
            long_path,
            payload(import_state(self.external)),
            active_source=self.source,
            existing_asset=None,
        )
        report = self.manager.inspect(
            long_path,
            result.dxf_asset,
            import_state(self.external),
            repair=False,
        )

        self.assertEqual(report.status, DxfStatus.READY)

    def test_dxf_copy_interruption_leaves_the_old_project_untouched(self):
        first = self.save()
        old_json = self.project_path.read_bytes()
        old_dxf = (self.project_path.parent / "source" / "source.dxf").read_bytes()
        replacement = create_dxf(self.root / "replacement.dxf", offset=4000)

        def fail(stage):
            if stage == "dxf_copied_to_temp":
                raise OSError("simulated copy interruption")

        with self.assertRaisesRegex(ProjectPersistenceError, "DXF 複製失敗"):
            DxfAssetManager(failure_hook=fail).save_project(
                self.project_path,
                payload(import_state(replacement, offset=4000)),
                active_source=self.manager.verified_source(
                    replacement, DxfStatus.RUNTIME_READY
                ),
                existing_asset=first.dxf_asset,
            )

        self.assertEqual(self.project_path.read_bytes(), old_json)
        self.assertEqual(
            (self.project_path.parent / "source" / "source.dxf").read_bytes(),
            old_dxf,
        )

    def test_json_failure_after_dxf_replace_rolls_back_both_files(self):
        first = self.save()
        old_json = self.project_path.read_bytes()
        managed = self.project_path.parent / "source" / "source.dxf"
        old_dxf = managed.read_bytes()
        replacement = create_dxf(self.root / "replacement.dxf", offset=4000)

        def fail(stage):
            if stage == "dxf_replaced":
                raise OSError("simulated json replacement interruption")

        with self.assertRaisesRegex(
            ProjectPersistenceError, "project.json 正式檔案替換失敗"
        ):
            DxfAssetManager(failure_hook=fail).save_project(
                self.project_path,
                payload(import_state(replacement, offset=4000)),
                active_source=self.manager.verified_source(
                    replacement, DxfStatus.RUNTIME_READY
                ),
                existing_asset=first.dxf_asset,
            )

        self.assertEqual(self.project_path.read_bytes(), old_json)
        self.assertEqual(managed.read_bytes(), old_dxf)

    def test_json_staging_failure_never_replaces_the_managed_copy(self):
        first = self.save()
        old_json = self.project_path.read_bytes()
        managed = self.project_path.parent / "source" / "source.dxf"
        old_dxf = managed.read_bytes()
        replacement = create_dxf(self.root / "replacement.dxf", offset=4000)

        def fail(stage):
            if stage == "json_written_to_temp":
                raise OSError("simulated json staging interruption")

        with self.assertRaisesRegex(ProjectPersistenceError, "JSON 寫入失敗"):
            DxfAssetManager(failure_hook=fail).save_project(
                self.project_path,
                payload(import_state(replacement, offset=4000)),
                active_source=self.manager.verified_source(
                    replacement, DxfStatus.RUNTIME_READY
                ),
                existing_asset=first.dxf_asset,
            )

        self.assertEqual(self.project_path.read_bytes(), old_json)
        self.assertEqual(managed.read_bytes(), old_dxf)


class DxfCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.checker = DxfCompatibilityChecker()
        self.source = Path("source.dxf")
        self.saved = import_state(self.source, handle="10")
        self.rows = {
            "walers": [{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 3000,
                "EndY": 0,
            }],
            "struts": [],
            "braces": [],
        }

    def test_handle_change_with_same_layer_and_engineering_line_is_compatible(self):
        candidate = import_state(self.source, handle="99")

        report = self.checker.compare(self.saved, candidate, self.rows)

        self.assertEqual(report.status, DxfStatus.GEOMETRY_COMPATIBLE)
        self.assertEqual(report.geometry_match_count, 1)
        self.assertEqual(report.binding_required_ids, ())

    def test_layer_change_with_same_engineering_line_is_a_compatible_candidate(self):
        candidate = import_state(self.source, handle="99", layer="RENAMED")

        report = self.checker.compare(self.saved, candidate, self.rows)

        self.assertEqual(report.status, DxfStatus.GEOMETRY_COMPATIBLE)
        self.assertEqual(report.layer_changed_match_count, 1)
        merged = self.checker.merge_source_references(
            self.saved,
            candidate,
            report,
            source_path=self.source,
        )
        self.assertEqual(
            merged["converted"]["walers"][0]["source_layer"],
            "RENAMED",
        )
        self.assertEqual(
            merged["converted"]["walers"][0]["selection_source"],
            "manual",
        )

    def test_geometry_change_is_not_silently_accepted(self):
        candidate = import_state(self.source, handle="99", offset=1000)

        report = self.checker.compare(self.saved, candidate, self.rows)

        self.assertEqual(report.status, DxfStatus.INCOMPATIBLE)
        self.assertIn("W1", report.binding_required_ids)

    def test_critical_component_count_change_is_incompatible(self):
        candidate = copy.deepcopy(self.saved)
        extra = copy.deepcopy(candidate["converted"]["walers"][0])
        extra["id"] = "W2"
        extra["start"] = extra["world_start"] = [0.0, 1000.0]
        extra["end"] = extra["world_end"] = [3000.0, 1000.0]
        candidate["converted"]["walers"].append(extra)

        report = self.checker.compare(self.saved, candidate, self.rows)

        self.assertEqual(report.status, DxfStatus.INCOMPATIBLE)
        self.assertTrue(any("構件數量不同" in item for item in report.incompatible_items))

    def test_solver_geometry_mismatch_is_incompatible(self):
        changed_rows = copy.deepcopy(self.rows)
        changed_rows["walers"][0]["EndX"] = 2500

        report = self.checker.compare(self.saved, self.saved, changed_rows)

        self.assertEqual(report.status, DxfStatus.INCOMPATIBLE)
        self.assertTrue(any("Solver 工程線" in item for item in report.incompatible_items))

    def test_append_remapped_solver_id_is_validated_by_geometry(self):
        remapped_rows = copy.deepcopy(self.rows)
        remapped_rows["walers"][0]["WalerID"] = "W5"

        report = self.checker.compare(self.saved, self.saved, remapped_rows)

        self.assertEqual(report.status, DxfStatus.GEOMETRY_COMPATIBLE)
        self.assertEqual(report.incompatible_items, ())

    def test_legacy_missing_state_can_adopt_candidate_without_changing_solver_ids(self):
        candidate = import_state(self.source, handle="99")
        candidate["converted"]["walers"][0]["id"] = "W77"

        report = self.checker.compare_candidate_to_solver(candidate, self.rows)
        adopted = self.checker.adopt_candidate_state_for_solver(
            candidate,
            report,
            source_path=self.source,
        )

        self.assertEqual(report.status, DxfStatus.GEOMETRY_COMPATIBLE)
        self.assertEqual(adopted["converted"]["walers"][0]["id"], "W1")


class MainProjectPersistenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def app(self):
        app = SupportInputApp.__new__(SupportInputApp)
        app.root = None
        app.project_cases_dir = self.root
        app.project_data = ProjectDataModel()
        app.result_items = {}
        app.project_result = None
        app.last_calculated_time = None
        app.current_project_path = None
        app.project_dirty = True
        app.project_dirty_reason = "test"
        app.dxf_last_import_debug = None
        app.dxf_asset = None
        app.dxf_asset_status_report = None
        app.last_dxf_compatibility_report = None
        app.dxf_asset_manager = DxfAssetManager()
        app.dxf_compatibility_checker = DxfCompatibilityChecker()
        app.solver_memory = {}
        app.support_candidate_cache = {}
        app._refresh_tree = lambda _name: None
        app._refresh_results_tree = lambda **_kwargs: None
        app._refresh_project_case_list = lambda **_kwargs: None
        app.update_preview = lambda **_kwargs: None
        app.show_result = lambda _text: None
        return app

    def test_save_failure_does_not_clear_dirty_state(self):
        app = self.app()

        def fail(stage):
            if stage == "json_written_to_temp":
                raise OSError("simulated json failure")

        app.dxf_asset_manager = DxfAssetManager(failure_hook=fail)

        with self.assertRaises(ProjectPersistenceError):
            app.save_project_case("dirty")

        self.assertTrue(app.project_dirty)

    def test_support_solver_diagnostics_round_trip_is_optional(self):
        app = self.app()
        diagnostics = SolverDiagnostics(
            solver_type="support",
            search_stage="ENHANCED",
            legal_solution_found=True,
        )
        solution = support.GlobalSolution(
            plans=[],
            total_score=10,
            valid=True,
            search_diagnostics=diagnostics.to_dict(),
        )

        payload = app._serialize_result_item(
            "Z1",
            {"type": "support", "result": solution, "visible": True},
        )
        restored = app._deserialize_result_item(payload)

        self.assertEqual(
            restored["result"].search_diagnostics["search_stage"],
            "ENHANCED",
        )
        legacy_payload = copy.deepcopy(payload)
        legacy_payload["result"].pop("search_diagnostics")
        legacy = app._deserialize_result_item(legacy_payload)
        self.assertEqual(legacy["result"].search_diagnostics, {})

    def test_main_save_wires_import_state_to_managed_project_asset(self):
        app = self.app()
        dxf_path = create_dxf(self.root / "runtime source.dxf")
        app.dxf_last_import_debug = import_state(dxf_path)

        saved_path = app.save_project_case("主程式專案")

        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        self.assertTrue((saved_path.parent / "source" / "source.dxf").is_file())
        self.assertEqual(saved["dxf_asset"]["storage_mode"], "managed_copy")
        self.assertEqual(app.dxf_asset_status_report.status, DxfStatus.READY)
        self.assertFalse(app.project_dirty)

    def test_current_null_state_loads_solver_result_and_disables_dxf_export(self):
        app = self.app()
        legacy_result = {
            "last_calculated_time": "2026-01-01T00:00:00",
            "best_solution": {
                "result_items": [{
                    "id": "W1-plan-1",
                    "type": "waler",
                    "visible": True,
                    "result": {
                        "waler_id": "W1",
                        "selected_plan": {"pieces": [["steel", 3000]], "gap": 0},
                    },
                }]
            },
        }
        project_path = self.root / "manual.json"
        project_path.write_text(
            json.dumps(payload(None, result=legacy_result), ensure_ascii=False),
            encoding="utf-8",
        )

        app.load_project_case("manual", silent=True)

        self.assertIn("W1-plan-1", app.result_items)
        self.assertEqual(
            app.dxf_asset_status_report.status,
            DxfStatus.NO_DXF,
        )
        self.assertFalse(app.dxf_asset_status_report.can_export)
        self.assertFalse(app.project_dirty)

    def test_legacy_state_without_asset_migrates_to_managed_copy_on_save(self):
        app = self.app()
        dxf_path = create_dxf(self.root / "legacy-source.dxf")
        legacy_payload = payload(import_state(dxf_path))
        (self.root / "legacy-linked.json").write_text(
            json.dumps(legacy_payload, ensure_ascii=False),
            encoding="utf-8",
        )

        app.load_project_case("legacy-linked", silent=True)
        self.assertEqual(
            app.dxf_asset_status_report.status,
            DxfStatus.RELINK_REQUIRED,
        )
        self.assertTrue(app.dxf_asset_status_report.original_exists)

        saved_path = app.save_project_case("legacy-linked")

        self.assertTrue((saved_path.parent / "source" / "source.dxf").is_file())
        self.assertEqual(app.dxf_asset_status_report.status, DxfStatus.READY)

    def test_new_manual_project_with_results_is_not_misclassified_as_damaged(self):
        app = self.app()
        manual_result = {
            "last_calculated_time": "2026-01-01T00:00:00",
            "best_solution": {
                "result_items": [{
                    "id": "W1-plan-1",
                    "type": "waler",
                    "visible": True,
                    "result": {"waler_id": "W1", "selected_plan": {}},
                }]
            },
        }
        manual_path = self.root / "manual.json"
        manual_path.write_text(
            json.dumps(payload(None, result=manual_result), ensure_ascii=False),
            encoding="utf-8",
        )

        app.load_project_case("manual", silent=True)

        self.assertEqual(app.dxf_asset_status_report.status, DxfStatus.NO_DXF)
        self.assertIn("W1-plan-1", app.result_items)

    def test_project_missing_required_dxf_state_is_rejected_by_structure(self):
        app = self.app()
        legacy_result = {
            "last_calculated_time": "2026-01-01T00:00:00",
            "best_solution": {
                "result_items": [{
                    "id": "W1-plan-1",
                    "type": "waler",
                    "visible": True,
                    "result": {
                        "waler_id": "W1",
                        "selected_plan": {"pieces": [["steel", 3000]], "gap": 0},
                    },
                }]
            },
        }
        legacy_payload = payload(None, result=legacy_result)
        legacy_payload.pop("dxf_asset")
        legacy_payload.pop("schema_version")
        (self.root / "legacy.json").write_text(
            json.dumps(legacy_payload, ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaises(ProjectPersistenceError) as raised:
            app.load_project_case("legacy", silent=True)

        self.assertIn("dxf_asset", raised.exception.detail)

    def test_exact_relink_keeps_solver_results_and_manual_corrections(self):
        app = self.app()
        dxf_path = create_dxf(self.root / "relink.dxf")
        info = DxfAssetManager.file_info(dxf_path)
        app.dxf_last_import_debug = import_state(dxf_path)
        app.dxf_asset = {"sha256": info.sha256}
        app.result_items = {"kept": {"material": "unchanged"}}
        app.cad_import_status = ""
        app.cad_last_event = None
        app.cad_last_error = None
        before_results = copy.deepcopy(app.result_items)

        with patch("main.filedialog.askopenfilename", return_value=str(dxf_path)):
            app._relink_dxf()

        self.assertEqual(app.result_items, before_results)
        self.assertEqual(
            app.dxf_last_import_debug["converted"]["walers"][0]["selection_source"],
            "manual",
        )
        self.assertEqual(
            app.dxf_asset_status_report.status,
            DxfStatus.VERIFIED_PENDING_SAVE,
        )
        self.assertTrue(app.project_dirty)


class ProjectSavedStatusLabelTests(unittest.TestCase):
    class Variable:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    def render_status(self, *, path, dirty):
        app = SupportInputApp.__new__(SupportInputApp)
        app.current_project_path = path
        app.project_dirty = dirty
        app.project_asset_status_var = self.Variable()
        app.dxf_asset_status_report = None
        app.last_dxf_compatibility_report = None
        app.result_items = {}
        app._refresh_project_status_display()
        return app.project_asset_status_var.value

    def test_saved_project_uses_positive_saved_wording(self):
        status = self.render_status(
            path=Path("C:/projects/Y1A/project.json"),
            dirty=False,
        )
        self.assertIn("是否儲存：是", status)
        self.assertNotIn("尚未儲存", status)

    def test_dirty_or_never_saved_project_reports_not_saved(self):
        dirty_status = self.render_status(
            path=Path("C:/projects/Y1A/project.json"),
            dirty=True,
        )
        new_status = self.render_status(path=None, dirty=False)

        self.assertIn("是否儲存：否", dirty_status)
        self.assertIn("是否儲存：否", new_status)


if __name__ == "__main__":
    unittest.main()
