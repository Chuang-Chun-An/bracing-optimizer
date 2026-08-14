from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ezdxf

import dxf_result_export as exporter
from dxf_result_export import (
    APP_ID,
    JACK_BLOCK_NAME,
    RESULT_SUPPORT_LAYER,
    RESULT_WALER_LAYER,
    DXFAuditIssue,
    DXFAuditSummary,
    DXFExportValidationError,
    ExportPiece,
    MemberBinding,
    MemberExportPlan,
    build_member_bindings,
    export_results_to_dxf,
)


ROOT = Path(__file__).resolve().parents[1]
SPECIAL_SOURCE = ROOT / "project_cases" / "Y1A站第一層支撐" / "source" / "source.dxf"
SPECIAL_PROJECT = ROOT / "project_cases" / "Y1A站第一層支撐" / "project.json"


def validation_state(*, source_path: str = "") -> dict:
    return {
        "source_path": source_path,
        "coordinate_system": {"mode": "world", "origin_x": 0, "origin_y": 0},
        "validation_messages": [],
        "selected_layers": {
            "waler": "WALER_SOURCE",
            "strut": "STRUT_SOURCE",
        },
        "source_geometry": [
            {
                "role": "waler",
                "source_handle": "SOURCE-W",
                "points": [[10_000, -20_000], [13_000, -20_000]],
                "closed": False,
                "source_layer": "WALER_SOURCE",
                "source_entity_type": "LINE",
            },
            {
                "role": "strut",
                "source_handle": "SOURCE-S",
                "points": [[15_000, -20_000], [15_000, -17_400]],
                "closed": False,
                "source_layer": "STRUT_SOURCE",
                "source_entity_type": "LINE",
            },
        ],
        "converted": {
            "walers": [
                {
                    "id": "W1",
                    "source_layer": "WALER_SOURCE",
                    "start": [10_000, -20_000],
                    "end": [13_000, -20_000],
                    "world_start": [10_000, -20_000],
                    "world_end": [13_000, -20_000],
                }
            ],
            "struts": [
                {
                    "id": "S1",
                    "source_layer": "STRUT_SOURCE",
                    "start": [15_000, -20_000],
                    "end": [15_000, -17_400],
                    "world_start": [15_000, -20_000],
                    "world_end": [15_000, -17_400],
                }
            ],
            "braces": [],
            "corner_braces": [],
            "columns": [],
            "beams": [],
        },
    }


def validation_bindings() -> dict[tuple[str, str], MemberBinding]:
    return {
        ("waler", "W1"): MemberBinding(
            "W1", "waler", "WALER_SOURCE", (10_000, -20_000), (13_000, -20_000)
        ),
        ("strut", "S1"): MemberBinding(
            "S1", "strut", "STRUT_SOURCE", (15_000, -20_000), (15_000, -17_400)
        ),
    }


def validation_plans() -> tuple[MemberExportPlan, ...]:
    return (
        MemberExportPlan(
            "W1", "waler", (ExportPiece("steel", 3000),), result_id="W1-test"
        ),
        MemberExportPlan(
            "S1",
            "strut",
            (ExportPiece("steel", 2000), ExportPiece("jack", 600)),
            result_id="S1-test",
        ),
    )


class DXFCleanExportValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _export(self, output_path: Path | None = None):
        return export_results_to_dxf(
            validation_state(),
            output_path or self.temp_path / "result.dxf",
            validation_plans(),
            validation_bindings(),
        )

    def _assert_old_output_preserved(self, output_path: Path, original: bytes):
        self.assertTrue(output_path.is_file())
        self.assertEqual(original, output_path.read_bytes())

    def test_final_file_is_auditable_and_has_no_imported_history_objects(self):
        output_path = self.temp_path / "一般 中文路徑 clean.dxf"

        report = self._export(output_path)

        document = ezdxf.readfile(output_path)
        auditor = document.audit()
        self.assertEqual(0, len(auditor.errors))
        self.assertEqual(0, len(auditor.fixes))
        self.assertEqual(0, report.final_audit.error_count)
        self.assertEqual(0, report.final_audit.fix_count)
        self.assertFalse(
            [entity for entity in document.objects if entity.dxftype() == "XRECORD"]
        )
        raw = output_path.read_text(encoding="utf-8")
        self.assertNotIn("_LAYISO_STATE", raw)
        self.assertNotIn("ADSK_XREC_LAYER_RECONCILED", raw)

        layer_records = [
            entity
            for entity in document.entitydb.values()
            if entity is not None and entity.is_alive and entity.dxftype() == "LAYER"
        ]
        layer_names = [entity.dxf.name.casefold() for entity in layer_records]
        self.assertEqual(len(layer_names), len(set(layer_names)))

    def test_formal_export_never_reads_or_saves_the_original_source(self):
        source_path = self.temp_path / "original source.dxf"
        source_document = ezdxf.new("R2010")
        source_document.modelspace().add_circle((1, 2), 3)
        source_document.saveas(source_path)
        original_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        state = validation_state(source_path=str(source_path))
        output_path = self.temp_path / "clean result.dxf"
        real_readfile = exporter.ezdxf.readfile
        read_paths: list[Path] = []
        save_paths: list[Path] = []
        real_save = exporter._save_clean_document

        def track_read(path, *args, **kwargs):
            read_paths.append(Path(path).resolve())
            return real_readfile(path, *args, **kwargs)

        def track_save(document, path):
            save_paths.append(Path(path).resolve())
            return real_save(document, path)

        with mock.patch.object(exporter.ezdxf, "readfile", side_effect=track_read), mock.patch.object(
            exporter, "_save_clean_document", side_effect=track_save
        ):
            export_results_to_dxf(
                state,
                output_path,
                validation_plans(),
                validation_bindings(),
            )

        self.assertNotIn(source_path.resolve(), read_paths)
        self.assertNotIn(source_path.resolve(), save_paths)
        self.assertNotIn(output_path.resolve(), save_paths)
        self.assertEqual(1, len(save_paths))
        self.assertEqual(original_hash, hashlib.sha256(source_path.read_bytes()).hexdigest())

    def test_missing_original_source_still_exports_from_saved_project_geometry(self):
        missing = self.temp_path / "deleted original.dxf"
        output_path = self.temp_path / "independent result.dxf"

        report = export_results_to_dxf(
            validation_state(source_path=str(missing)),
            output_path,
            validation_plans(),
            validation_bindings(),
        )

        self.assertFalse(missing.exists())
        self.assertTrue(output_path.is_file())
        self.assertEqual(0, report.final_audit.error_count)
        self.assertEqual(0, report.final_audit.fix_count)

    def test_invalid_or_result_colliding_source_layers_use_central_fallbacks(self):
        state = validation_state()
        state["source_geometry"][0]["source_layer"] = "BAD/LAYER"
        state["converted"]["walers"][0]["source_layer"] = "BAD/LAYER"
        state["source_geometry"][1]["source_layer"] = RESULT_SUPPORT_LAYER
        state["converted"]["struts"][0]["source_layer"] = RESULT_SUPPORT_LAYER
        output_path = self.temp_path / "fallback.dxf"

        report = export_results_to_dxf(
            state, output_path, validation_plans(), validation_bindings()
        )

        self.assertEqual(2, len(report.layer_name_fallbacks))
        fallback_names = {item.output_name for item in report.layer_name_fallbacks}
        self.assertEqual(2, len(fallback_names))
        self.assertTrue(all(name.startswith("SD_BASE_") for name in fallback_names))
        document = ezdxf.readfile(output_path)
        self.assertIn(RESULT_WALER_LAYER, document.layers)
        self.assertIn(RESULT_SUPPORT_LAYER, document.layers)
        self.assertTrue(all(name in document.layers for name in fallback_names))
        self.assertFalse(any(entity.dxf.layer == "BAD/LAYER" for entity in document.modelspace()))

    def test_result_coordinates_and_layers_survive_staged_reread(self):
        output_path = self.temp_path / "coordinates.dxf"
        report = self._export(output_path)
        document = ezdxf.readfile(output_path)
        dimensions = [
            entity
            for entity in document.modelspace().query("DIMENSION")
            if entity.has_xdata(APP_ID)
        ]
        jacks = [
            entity
            for entity in document.modelspace().query("INSERT")
            if entity.dxf.name == JACK_BLOCK_NAME
        ]

        self.assertEqual(report.dimension_count, len(dimensions))
        self.assertEqual(report.jack_count, len(jacks))
        self.assertEqual({RESULT_WALER_LAYER, RESULT_SUPPORT_LAYER}, {entity.dxf.layer for entity in dimensions})
        self.assertEqual(RESULT_SUPPORT_LAYER, jacks[0].dxf.layer)
        self.assertEqual((10_000.0, -20_000.0), tuple(dimensions[0].dxf.defpoint2)[:2])

    @unittest.skipUnless(SPECIAL_PROJECT.is_file(), "Y1A project fixture is unavailable")
    def test_y1a_special_project_exports_clean_without_reading_duplicate_layer_source(self):
        project = json.loads(SPECIAL_PROJECT.read_text(encoding="utf-8"))
        state = project["dxf_import_state"]
        bindings = build_member_bindings(
            state,
            project["input_data"]["walers"],
            project["input_data"]["struts"],
        )
        waler = bindings[("waler", "W1")]
        strut = bindings[("strut", "S1")]
        waler_length = math.dist(waler.world_start, waler.world_end)
        strut_length = math.dist(strut.world_start, strut.world_end)
        plans = (
            MemberExportPlan(
                "W1", "waler", (ExportPiece("steel", waler_length),), result_id="Y1A-W1"
            ),
            MemberExportPlan(
                "S1",
                "strut",
                (ExportPiece("steel", strut_length - 600), ExportPiece("jack", 600)),
                result_id="Y1A-S1",
            ),
        )
        output_path = self.temp_path / "Y1A clean result.dxf"
        source_hash = (
            hashlib.sha256(SPECIAL_SOURCE.read_bytes()).hexdigest()
            if SPECIAL_SOURCE.is_file()
            else None
        )

        report = export_results_to_dxf(state, output_path, plans, bindings)

        self.assertEqual(0, report.final_audit.error_count)
        self.assertEqual(0, report.final_audit.fix_count)
        self.assertEqual(report.dimension_count, report.actual_dimension_count)
        self.assertEqual(report.jack_count, report.actual_jack_count)
        self.assertEqual(
            {"waler", "strut", "brace", "corner_brace", "column", "beam", "auxiliary"},
            {role for role, _count in report.background_counts},
        )
        document = ezdxf.readfile(output_path)
        self.assertFalse(
            [entity for entity in document.objects if entity.dxftype() == "XRECORD"]
        )
        self.assertEqual(0, len(document.audit().errors))
        self.assertEqual(0, len(document.audit().fixes))
        if source_hash is not None:
            self.assertEqual(source_hash, hashlib.sha256(SPECIAL_SOURCE.read_bytes()).hexdigest())

    def test_first_staged_save_failure_does_not_create_or_overwrite_final(self):
        for existing in (False, True):
            with self.subTest(existing=existing):
                output_path = self.temp_path / f"save-failure-{existing}.dxf"
                original = b"existing-final" if existing else None
                if original is not None:
                    output_path.write_bytes(original)
                with mock.patch.object(
                    exporter,
                    "_save_clean_document",
                    side_effect=OSError("injected staged save failure"),
                ):
                    with self.assertRaises(DXFExportValidationError) as raised:
                        self._export(output_path)
                if original is None:
                    self.assertFalse(output_path.exists())
                else:
                    self._assert_old_output_preserved(output_path, original)
                self.assertTrue(raised.exception.temporary_path.exists())

    def test_nonzero_final_audit_does_not_overwrite_final(self):
        output_path = self.temp_path / "audit-failure.dxf"
        original = b"existing-final"
        output_path.write_bytes(original)
        issue = DXFAuditIssue(
            "fix", 9999, "INJECTED_FIX", "injected final audit fix"
        )
        injected = DXFAuditSummary(
            fixes=(issue,), fix_types=((issue.issue_type, 1),)
        )

        with mock.patch.object(exporter, "_audit_summary", return_value=injected):
            with self.assertRaises(DXFExportValidationError) as raised:
                self._export(output_path)

        self._assert_old_output_preserved(output_path, original)
        self.assertEqual(1, raised.exception.final_audit.fix_count)
        self.assertTrue(raised.exception.temporary_path.is_file())

    def test_engineering_validation_failure_does_not_overwrite_final(self):
        output_path = self.temp_path / "geometry-failure.dxf"
        original = b"existing-final"
        output_path.write_bytes(original)
        with mock.patch.object(
            exporter,
            "_validate_results",
            side_effect=DXFExportValidationError("成果座標不符"),
        ):
            with self.assertRaises(DXFExportValidationError) as raised:
                self._export(output_path)

        self._assert_old_output_preserved(output_path, original)
        self.assertIn("成果座標不符", str(raised.exception))
        self.assertTrue(raised.exception.temporary_path.is_file())

    def test_atomic_replace_failure_preserves_existing_final(self):
        output_path = self.temp_path / "replace-failure.dxf"
        original = b"existing-final"
        output_path.write_bytes(original)
        with mock.patch.object(
            exporter,
            "_replace_validated_file",
            side_effect=OSError("injected replace failure"),
        ):
            with self.assertRaises(DXFExportValidationError) as raised:
                self._export(output_path)

        self._assert_old_output_preserved(output_path, original)
        self.assertIn("交易式替換失敗", str(raised.exception))
        self.assertTrue(raised.exception.temporary_path.is_file())


if __name__ == "__main__":
    unittest.main()
