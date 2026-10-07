import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ezdxf
from bracing_optimizer.algorithms import support

from main import SupportInputApp
from bracing_optimizer.algorithms.solver_search import SolverDiagnostics
from bracing_optimizer.application.project_data import ProjectDataModel, TABLE_COLUMNS
from bracing_optimizer.application.project_service import PausedReviewRelinkRequest
from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfCompatibilityChecker,
    DxfStatus,
    DxfWorkflowStatus,
    MANAGED_DXF_RELATIVE_PATH,
    PROJECT_SCHEMA_VERSION,
    PROJECT_ROW_SCHEMA_ERROR_STAGE,
    PROJECT_SCHEMA_UNREADABLE_STAGE,
    ProjectPersistenceError,
    ProjectSerializer,
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
    input_data = ProjectDataModel(
        walers=[{
            "WalerID": "W1",
            "StartX": 0,
            "StartY": 0,
            "EndX": 3000,
            "EndY": 0,
        }],
    ).to_case_data()
    return {
        "schema_version": 3,
        "project_information": {"project_name": "測試專案"},
        "input_data": input_data,
        "dxf_import_state": copy.deepcopy(state),
        "dxf_asset": None,
        "result": result,
    }


class ProjectSchemaCompatibilityTests(unittest.TestCase):
    def test_current_table_contract_accepts_exact_rows_and_optional_tables(self):
        project_payload = payload()

        ProjectSerializer.validate_for_load(project_payload)

        for table_name, rows in project_payload["input_data"].items():
            for row in rows:
                self.assertEqual(set(row), set(TABLE_COLUMNS[table_name]))

        project_payload["input_data"].pop("inventory")
        project_payload["input_data"].pop("material_specs")
        ProjectSerializer.validate_for_load(project_payload)

    def test_direct_validation_rejects_missing_and_unsupported_row_fields(self):
        cases = (
            ("missing", lambda row: row.pop("Remark"), "缺少欄位", "Remark"),
            (
                "unsupported",
                lambda row: row.__setitem__("Unexpected", True),
                "不支援欄位",
                "Unexpected",
            ),
        )
        for name, mutate, reason, field_name in cases:
            with self.subTest(name=name):
                project_payload = payload()
                mutate(project_payload["input_data"]["walers"][0])

                with self.assertRaises(ProjectPersistenceError) as raised:
                    ProjectSerializer.validate(project_payload)

                self.assertEqual(
                    raised.exception.stage,
                    PROJECT_ROW_SCHEMA_ERROR_STAGE,
                )
                self.assertIn("input_data.walers[1]", raised.exception.detail)
                self.assertIn(reason, raised.exception.detail)
                self.assertIn(field_name, raised.exception.detail)

    def test_direct_validation_rejects_unsupported_input_table(self):
        project_payload = payload()
        project_payload["input_data"]["legacy_table"] = []

        with self.assertRaises(ProjectPersistenceError) as raised:
            ProjectSerializer.validate(project_payload)

        self.assertEqual(raised.exception.stage, PROJECT_ROW_SCHEMA_ERROR_STAGE)
        self.assertIn("不支援資料表", raised.exception.detail)
        self.assertIn("legacy_table", raised.exception.detail)

    def test_row_schema_mismatch_uses_same_load_error_for_compatible_versions(self):
        for version in (None, PROJECT_SCHEMA_VERSION - 1, PROJECT_SCHEMA_VERSION):
            with self.subTest(version=version):
                project_payload = payload()
                if version is None:
                    project_payload.pop("schema_version")
                else:
                    project_payload["schema_version"] = version
                project_payload["input_data"]["walers"][0].pop("Remark")

                with self.assertRaises(ProjectPersistenceError) as raised:
                    ProjectSerializer.validate_for_load(project_payload)

                self.assertEqual(
                    raised.exception.stage,
                    PROJECT_SCHEMA_UNREADABLE_STAGE,
                )
                self.assertIn("底層驗證錯誤", raised.exception.detail)
                self.assertIn("input_data.walers[1]", raised.exception.detail)
                self.assertIn("Remark", raised.exception.detail)

    def test_load_validation_rejects_non_integer_and_out_of_range_versions(self):
        invalid_versions = ("3", 3.0, True, False, None, 0, -1)

        for index, version in enumerate(invalid_versions):
            with self.subTest(version=version, value_type=type(version).__name__):
                project_payload = payload()
                project_payload["schema_version"] = version

                with self.assertRaises(ProjectPersistenceError) as raised:
                    ProjectSerializer.validate_for_load(project_payload)

                self.assertIn("schema_version", raised.exception.stage)

    def test_load_validation_classifies_version_before_current_structure(self):
        future_payload = payload()
        future_payload["schema_version"] = PROJECT_SCHEMA_VERSION + 1
        future_payload.pop("dxf_asset")

        with self.assertRaises(ProjectPersistenceError) as future_error:
            ProjectSerializer.validate_for_load(future_payload)

        self.assertIn("版本不相容", future_error.exception.stage)
        self.assertIn("高於目前支援版本", future_error.exception.detail)

    def test_load_validation_reuses_current_structure_validation(self):
        for version in (None, PROJECT_SCHEMA_VERSION - 1):
            with self.subTest(version=version):
                project_payload = payload()
                if version is None:
                    project_payload.pop("schema_version")
                else:
                    project_payload["schema_version"] = version
                project_payload.pop("dxf_asset")

                with self.assertRaises(ProjectPersistenceError) as raised:
                    ProjectSerializer.validate_for_load(project_payload)

                self.assertIn("無法以現行格式讀取", raised.exception.stage)
                self.assertIn("dxf_asset", raised.exception.detail)

        current_payload = payload()
        current_payload.pop("dxf_asset")
        with self.assertRaises(ProjectPersistenceError) as current_error:
            ProjectSerializer.validate_for_load(current_payload)

        self.assertEqual(current_error.exception.stage, "JSON 驗證失敗")
        self.assertIn("dxf_asset", current_error.exception.detail)


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

    def test_canonical_waler_tail_survives_project_file_save_and_load(self):
        canonical_plan = {
            "segments": [8000, 8000],
            "steel_length": 16000,
            "tail_adjustment": 300,
            "gap": 150,
            "pieces": [
                ["steel", 8000],
                ["steel", 8000],
                ["shim", 300],
            ],
            "valid": True,
        }
        project_payload = payload(None, result={
            "W1-plan": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "required_length": 16450,
                    "selected_plan": canonical_plan,
                },
            },
        })

        self.manager.save_project(
            self.project_path,
            project_payload,
            active_source=None,
            existing_asset=None,
        )
        restored = json.loads(self.project_path.read_text(encoding="utf-8"))
        restored_plan = restored["result"]["W1-plan"]["result"][
            "selected_plan"
        ]

        self.assertEqual(restored["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(restored_plan, canonical_plan)

    def test_geometry_invalid_shared_zoning_round_trips_as_project_data(self):
        project_payload = payload()
        walers = [
            {"WalerID": "W1", "StartX": 0, "StartY": -10000,
             "EndX": 0, "EndY": 10000},
            {"WalerID": "W2", "StartX": 10000, "StartY": -10000,
             "EndX": 10000, "EndY": 10000},
        ]
        struts = [
            {"StrutID": "S1", "SharedLayoutGroup": "G1",
             "FromWaler": "W1", "ToWaler": "W2",
             "StartX": 0, "StartY": 0, "EndX": 10000, "EndY": 0,
             "Zoning": "USER-ZONE"},
            {"StrutID": "S2", "SharedLayoutGroup": "G1",
             "FromWaler": "W1", "ToWaler": "W2",
             "StartX": 0, "StartY": 1000, "EndX": 10000, "EndY": 2000,
             "Zoning": "USER-ZONE"},
        ]
        project_payload["input_data"] = ProjectDataModel(
            walers=walers,
            struts=struts,
        ).to_case_data()

        self.manager.save_project(
            self.project_path,
            project_payload,
            active_source=None,
            existing_asset=None,
        )
        saved = json.loads(self.project_path.read_text(encoding="utf-8"))
        restored = ProjectDataModel.from_case_data(saved["input_data"])

        self.assertEqual(
            [row["Zoning"] for row in restored.struts],
            ["USER-ZONE", "USER-ZONE"],
        )
        self.assertEqual(
            [row["SharedLayoutGroup"] for row in restored.struts],
            ["G1", "G1"],
        )

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

    def test_source_exclusion_state_round_trips_without_schema_change_or_dxf_write(self):
        before_bytes = self.external.read_bytes()
        before_mtime = self.external.stat().st_mtime_ns
        state = import_state(self.external)
        state["source_fingerprint"] = self.source.sha256.upper()
        state["excluded_sources"] = [
            {
                "role": "beam",
                "source_handles": ["6EF"],
                "source_layers": ["BEAM"],
                "source_entity_types": ["LWPOLYLINE"],
                "display_id_when_excluded": "待修-6EF",
                "reason": "user_excluded",
                "manual_override": None,
            }
        ]

        self.save(state=state)
        saved = json.loads(self.project_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["schema_version"], 3)
        self.assertEqual(saved["dxf_import_state"]["source_fingerprint"], self.source.sha256.upper())
        self.assertEqual(
            saved["dxf_import_state"]["excluded_sources"][0]["source_handles"],
            ["6EF"],
        )
        self.assertEqual(self.external.read_bytes(), before_bytes)
        self.assertEqual(self.external.stat().st_mtime_ns, before_mtime)

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
        self.assertFalse(managed.with_name(managed.name + ".rollback").exists())

    def test_rollback_failure_preserves_recovery_and_next_save_rejects_it(self):
        first = self.save()
        old_json = self.project_path.read_bytes()
        managed = self.project_path.parent / "source" / "source.dxf"
        old_dxf = managed.read_bytes()
        rollback = managed.with_name(managed.name + ".rollback")
        replacement = create_dxf(self.root / "replacement.dxf", offset=4000)
        replacement_source = self.manager.verified_source(
            replacement,
            DxfStatus.RUNTIME_READY,
        )

        def fail_after_dxf_replace(stage):
            if stage == "dxf_replaced":
                raise OSError("simulated json replacement interruption")

        real_replace = os.replace

        def fail_only_rollback(source, target):
            if Path(source) == rollback and Path(target) == managed:
                raise OSError("simulated rollback failure")
            return real_replace(source, target)

        with patch(
            "bracing_optimizer.infrastructure.project_persistence.os.replace",
            side_effect=fail_only_rollback,
        ), self.assertRaises(ProjectPersistenceError) as raised:
            DxfAssetManager(failure_hook=fail_after_dxf_replace).save_project(
                self.project_path,
                payload(import_state(replacement, offset=4000)),
                active_source=replacement_source,
                existing_asset=first.dxf_asset,
            )

        error = raised.exception
        self.assertEqual(error.stage, "交易回復失敗")
        self.assertEqual(error.recovery_path, rollback.resolve())
        self.assertEqual(error.managed_path, managed.resolve())
        self.assertTrue(rollback.is_file())
        self.assertEqual(rollback.read_bytes(), old_dxf)
        self.assertEqual(self.project_path.read_bytes(), old_json)

        before_json = self.project_path.read_bytes()
        before_managed = managed.read_bytes()
        before_recovery = rollback.read_bytes()
        with self.assertRaises(ProjectPersistenceError) as second:
            self.manager.save_project(
                self.project_path,
                payload(import_state(replacement, offset=4000)),
                active_source=replacement_source,
                existing_asset=first.dxf_asset,
            )

        self.assertEqual(second.exception.stage, "儲存前檢查失敗")
        self.assertEqual(second.exception.recovery_path, rollback.resolve())
        self.assertEqual(self.project_path.read_bytes(), before_json)
        self.assertEqual(managed.read_bytes(), before_managed)
        self.assertEqual(rollback.read_bytes(), before_recovery)
        self.assertFalse(self.project_path.with_name("project.json.tmp").exists())
        self.assertFalse(managed.with_name("source.dxf.tmp").exists())

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

    def test_changed_content_relink_adopts_candidate_exclusion_scope(self):
        saved = copy.deepcopy(self.saved)
        saved["source_fingerprint"] = "OLD-SHA"
        saved["excluded_sources"] = [
            {"role": "beam", "source_handles": ["6EF"]}
        ]
        candidate = import_state(self.source, handle="99")
        candidate["source_fingerprint"] = "NEW-SHA"
        candidate["excluded_sources"] = []
        report = self.checker.compare(saved, candidate, self.rows)

        merged = self.checker.merge_source_references(
            saved,
            candidate,
            report,
            source_path=self.source,
        )

        self.assertTrue(report.compatible)
        self.assertEqual(merged["source_fingerprint"], "NEW-SHA")
        self.assertEqual(merged["excluded_sources"], [])

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
            adjacency_units=[{
                "unit_id": "S1",
                "member_ids": ["S1"],
            }],
            adjacency_pairs=[],
            phase2_executed=True,
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
        self.assertTrue(
            restored["result"].search_diagnostics["phase2_executed"]
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

    def test_paused_review_exact_relink_round_trips_after_save(self):
        app = self.app()
        source = create_dxf(self.root / "paused-source.dxf")
        candidate = self.root / "paused-renamed.dxf"
        shutil.copy2(source, candidate)
        state = import_state(source)
        state.update({
            "review_state_version": 2,
            "source_fingerprint": DxfAssetManager.file_info(
                source
            ).sha256.upper(),
            "review_confirmations": {"waler:10": "CONFIRMED"},
            "manual_overrides": [{"role": "waler", "source_handles": ["10"]}],
        })
        app.dxf_workflow_status = DxfWorkflowStatus.REVIEW
        app.dxf_last_import_debug = state
        app.dxf_asset_status_report = DxfAssetManager().runtime_report(source)
        app.project_dirty = False
        app.project_dirty_reason = ""

        service = app._ensure_project_service()
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )
        app._adopt_paused_review_relink(committed)

        self.assertIsNone(app.dxf_asset)
        self.assertEqual(
            app.dxf_asset_status_report.status,
            DxfStatus.VERIFIED_PENDING_SAVE,
        )
        self.assertFalse(
            (self.root / "paused-relinked" / MANAGED_DXF_RELATIVE_PATH).is_file()
        )

        saved_path = app.save_project_case("paused-relinked")
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
        loaded = self.app()
        loaded.load_project_case("paused-relinked", silent=True)
        resume_source, resume_fingerprint = loaded._review_resume_source()

        self.assertEqual(saved["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(saved["dxf_workflow_status"], "REVIEW")
        self.assertEqual(
            saved["dxf_import_state"]["source_path"],
            str(candidate.resolve()),
        )
        self.assertEqual(
            saved["dxf_import_state"]["review_confirmations"],
            state["review_confirmations"],
        )
        self.assertEqual(
            loaded._current_dxf_workflow_status(),
            DxfWorkflowStatus.REVIEW,
        )
        self.assertEqual(
            resume_source,
            saved_path.parent / MANAGED_DXF_RELATIVE_PATH,
        )
        self.assertEqual(
            resume_fingerprint,
            state["source_fingerprint"],
        )


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
