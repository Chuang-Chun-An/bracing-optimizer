import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import ezdxf

from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfStatus,
    DxfWorkflowStatus,
    ProjectPersistenceError,
)
from bracing_optimizer.application.project_data import TABLE_COLUMNS, ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import (
    ApplyDxfReviewRequest,
    BuildProjectPayloadRequest,
    ProjectService,
    RelinkDxfRequest,
    SaveProjectRequest,
)


class FakeReviewResult:
    def __init__(self, rows):
        self.rows = rows
        self.existing_rows = None

    def to_project_rows(self, existing_rows=None):
        self.existing_rows = existing_rows
        return self.rows


def project_payload(*, include_asset=True, result=None):
    value = {
        "schema_version": 3,
        "project_information": {},
        "input_data": {
            "walers": [],
            "struts": [],
            "braces": [],
        },
        "dxf_import_state": None,
        "result": result,
    }
    if include_asset:
        value["dxf_asset"] = None
    return value


def create_dxf(path: Path) -> Path:
    document = ezdxf.new("R2010")
    document.modelspace().add_line((0, 0), (1000, 0))
    document.saveas(path)
    return path


def import_state(path: Path, *, handle: str) -> dict:
    return {
        "source_path": str(path),
        "converted": {
            "walers": [{
                "id": "W1",
                "source_handles": [handle],
                "source_layer": "STRUCTURE",
                "source_entity_types": ["LINE"],
                "start": [0.0, 0.0],
                "end": [3000.0, 0.0],
                "world_start": [0.0, 0.0],
                "world_end": [3000.0, 0.0],
                "local_start": [0.0, 0.0],
                "local_end": [3000.0, 0.0],
                "selection_source": "manual",
            }],
            "struts": [],
            "braces": [],
        },
    }


def project_rows() -> dict:
    return {
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


class ProjectServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.service = ProjectService()

    def tearDown(self):
        self.temporary.cleanup()

    def test_save_project_returns_updated_asset_status(self):
        path = self.root / "case" / "project.json"
        result = self.service.save_project(
            SaveProjectRequest(
                project_path=path,
                payload=project_payload(),
                current_project_path=None,
                existing_asset=None,
                import_state=None,
                current_dxf_report=None,
                has_solver_result=False,
            )
        )

        self.assertTrue(result.project_path.is_file())
        self.assertEqual(result.dxf_status_report.status, DxfStatus.NO_DXF)
        self.assertIsNone(result.dxf_asset)

    def test_load_project_owns_current_schema_and_no_dxf_inspection(self):
        path = self.root / "manual.json"
        result_payload = {
            "best_solution": {"result_items": [{"id": "W1"}]},
        }
        path.write_text(
            json.dumps(
                project_payload(result=result_payload),
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        result = self.service.load_project(path)

        self.assertEqual(result.payload["schema_version"], 3)
        self.assertIsNone(result.payload["dxf_asset"])
        self.assertFalse(result.legacy_no_state)
        self.assertEqual(
            result.dxf_status_report.status,
            DxfStatus.NO_DXF,
        )

    def test_load_project_does_not_reject_current_structure_by_version(self):
        for version in (2, None):
            with self.subTest(version=version):
                path = self.root / f"project-{version}.json"
                saved_payload = project_payload()
                if version is None:
                    saved_payload.pop("schema_version")
                else:
                    saved_payload["schema_version"] = version
                path.write_text(json.dumps(saved_payload), encoding="utf-8")

                result = self.service.load_project(path)

                self.assertEqual(result.payload.get("schema_version"), version)

    def test_exact_relink_is_accepted_without_candidate_import(self):
        dxf_path = create_dxf(self.root / "same.dxf")
        info = DxfAssetManager.file_info(dxf_path)
        saved_state = {
            "source_path": "old.dxf",
            "converted": {"walers": []},
        }
        request = RelinkDxfRequest(
            candidate_path=dxf_path,
            saved_state=saved_state,
            existing_asset={"sha256": info.sha256},
            current_dxf_report=None,
            project_rows={},
        )

        result = self.service.try_exact_relink(request)

        self.assertIsNotNone(result)
        self.assertTrue(result.accepted)
        self.assertEqual(
            result.dxf_status_report.status,
            DxfStatus.VERIFIED_PENDING_SAVE,
        )
        self.assertEqual(result.relinked_state["source_path"], str(dxf_path.resolve()))
        self.assertEqual(saved_state["source_path"], "old.dxf")

    def test_imported_relink_candidate_is_compared_and_merged(self):
        dxf_path = create_dxf(self.root / "candidate.dxf")
        result = self.service.relink_dxf(
            RelinkDxfRequest(
                candidate_path=dxf_path,
                saved_state=import_state(dxf_path, handle="10"),
                existing_asset=None,
                current_dxf_report=None,
                project_rows=project_rows(),
                candidate_state=import_state(dxf_path, handle="99"),
            )
        )

        self.assertTrue(result.accepted)
        self.assertEqual(
            result.dxf_status_report.status,
            DxfStatus.VERIFIED_PENDING_SAVE,
        )
        self.assertEqual(
            result.relinked_state["converted"]["walers"][0]["source_handles"],
            ["99"],
        )

    def test_stage_dxf_replace_preserves_settings_and_invalidates_results(self):
        current = ProjectDataModel(
            walers=[{
                "WalerID": "W-OLD",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
            }],
            inventory=[{
                "ItemCode": "I1",
                "Spec": "H400",
                "Usage": "支撐",
                "Length": 6000,
                "Qty": 2,
            }],
            material_specs=[{"Usage": "支撐", "Spec": "H400"}],
        )
        source = FakeReviewResult({
            "walers": [{
                "WalerID": "W1",
                "StartX": 10,
                "StartY": 20,
                "EndX": 3010,
                "EndY": 20,
            }],
            "struts": [],
            "braces": [],
            "columns": [],
            "beams": [],
            "corner_braces": [],
        })

        staged = self.service.stage_dxf_review_apply(
            ApplyDxfReviewRequest(
                current_project_data=current,
                current_workflow_status=DxfWorkflowStatus.REVIEW,
                import_mode="replace",
                review_result=source,
            )
        )

        self.assertEqual([row["WalerID"] for row in staged.project_data.walers], ["W1"])
        self.assertEqual(staged.project_data.inventory, current.inventory)
        self.assertEqual(staged.project_data.material_specs, current.material_specs)
        self.assertEqual([row["WalerID"] for row in current.walers], ["W-OLD"])
        self.assertFalse(staged.project_results.result_items)
        self.assertEqual(staged.workflow_status, DxfWorkflowStatus.COMPLETED)
        self.assertTrue(staged.clear_solver_memory)
        self.assertTrue(staged.clear_support_candidate_cache)

    def test_stage_dxf_append_supplies_existing_rows_and_appends(self):
        current = ProjectDataModel(walers=[{
            "WalerID": "W1",
            "StartX": 0,
            "StartY": 0,
            "EndX": 1000,
            "EndY": 0,
        }])
        source = FakeReviewResult({
            "walers": [{
                "WalerID": "W2",
                "StartX": 0,
                "StartY": 1000,
                "EndX": 1000,
                "EndY": 1000,
            }],
            "struts": [],
            "braces": [],
            "columns": [],
            "beams": [],
            "corner_braces": [],
        })

        staged = self.service.stage_dxf_review_apply(
            ApplyDxfReviewRequest(
                current_project_data=current,
                current_workflow_status=DxfWorkflowStatus.REVIEW,
                import_mode="append",
                review_result=source,
            )
        )

        self.assertEqual([row["WalerID"] for row in staged.project_data.walers], ["W1", "W2"])
        self.assertEqual(source.existing_rows["walers"][0]["WalerID"], "W1")

    def test_stage_dxf_review_keeps_provenance_out_of_project_and_solver_rows(self):
        source = FakeReviewResult({
            "walers": [{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 3000,
                "EndY": 0,
                "source_handles": ("A1",),
                "source_layer": "WALER",
                "recognition_method": "outline_centerline",
                "confidence": 0.95,
            }],
            "struts": [],
            "braces": [],
            "columns": [{"ColumnID": "C1", "source_handles": ("C1",)}],
            "beams": [{"BeamID": "BM1", "source_handles": ("B1",)}],
            "corner_braces": [{"CornerBraceID": "CB1"}],
        })

        staged = self.service.stage_dxf_review_apply(
            ApplyDxfReviewRequest(
                current_project_data=ProjectDataModel(),
                current_workflow_status=DxfWorkflowStatus.REVIEW,
                import_mode="replace",
                review_result=source,
            )
        )

        row = staged.project_data.walers[0]
        self.assertEqual(set(row), set(TABLE_COLUMNS["walers"]))
        self.assertNotIn("source_handles", row)
        self.assertNotIn("source_layer", row)
        self.assertNotIn("recognition_method", row)
        self.assertNotIn("confidence", row)
        self.assertFalse(hasattr(staged.project_data, "columns"))
        self.assertFalse(hasattr(staged.project_data, "beams"))
        self.assertFalse(hasattr(staged.project_data, "corner_braces"))

    def test_stage_dxf_rejects_invalid_lifecycle_without_mutating_project(self):
        current = ProjectDataModel(walers=[{
            "WalerID": "W1",
            "StartX": 0,
            "StartY": 0,
            "EndX": 1000,
            "EndY": 0,
        }])
        before = current.to_case_data()
        source = FakeReviewResult({})

        with self.assertRaisesRegex(ValueError, "REVIEW"):
            self.service.stage_dxf_review_apply(
                ApplyDxfReviewRequest(
                    current_project_data=current,
                    current_workflow_status=DxfWorkflowStatus.NONE,
                    import_mode="replace",
                    review_result=source,
                )
            )

        self.assertEqual(current.to_case_data(), before)

    def test_hydrate_project_builds_models_without_aliasing_payload(self):
        payload = project_payload(result={
            "last_calculated_time": "2026-01-01T00:00:00",
            "best_solution": {
                "result_items": [{
                    "id": "W1-方案1",
                    "type": "waler",
                    "visible": True,
                    "result": {"waler_id": "W1", "selected_plan": {}},
                }],
            },
        })
        payload["dxf_workflow_status"] = "NONE"
        payload["input_data"]["walers"] = [{
            "WalerID": "W1",
            "StartX": 0,
            "StartY": 0,
            "EndX": 1000,
            "EndY": 0,
        }]

        hydrated = self.service.hydrate_project(payload)
        hydrated.project_data.walers[0]["StartX"] = 99

        self.assertEqual(payload["input_data"]["walers"][0]["StartX"], 0)
        self.assertIn("W1-方案1", hydrated.project_results.result_items)
        self.assertEqual(hydrated.workflow_status, DxfWorkflowStatus.NONE)

    def test_hydrate_project_uses_supplied_inventory_for_legacy_input(self):
        payload = project_payload()
        fallback = [{
            "ItemCode": "I1",
            "Spec": "H400",
            "Usage": "支撐",
            "Length": 6000,
            "Qty": 2,
        }]

        hydrated = self.service.hydrate_project(
            payload,
            default_inventory=fallback,
        )

        self.assertEqual(hydrated.project_data.inventory, fallback)

    def test_build_project_payload_owns_schema_and_material_summary(self):
        data = ProjectDataModel(inventory=[{
            "ItemCode": "I1",
            "Spec": "H400",
            "Usage": "圍令",
            "Length": 6000,
            "Qty": 3,
        }])
        results = ProjectResultModel(result_items={
            "W1-方案1": {
                "type": "waler",
                "visible": True,
                "result": {
                    "waler_id": "W1",
                    "material_spec": "H400",
                    "selected_plan": {"pieces": [("steel", 6000)]},
                },
            },
        })

        payload = self.service.build_project_payload(
            BuildProjectPayloadRequest(
                project_name="case-a",
                project_data=data,
                project_results=results,
                workflow_status=DxfWorkflowStatus.NONE,
                dxf_import_state=None,
                dxf_asset=None,
            ),
            now=lambda: datetime(2026, 1, 2, 3, 4, 5),
        )

        self.assertEqual(payload["schema_version"], 3)
        self.assertEqual(payload["project_information"]["project_name"], "case-a")
        self.assertEqual(payload["dxf_workflow_status"], "NONE")
        self.assertEqual(
            payload["result"]["material_summary"][0]["remaining_qty"],
            2,
        )

    def test_input_change_plan_centralizes_binding_and_result_invalidation(self):
        geometry = self.service.plan_input_change(
            table_name="struts",
            field_name="StartX",
        )
        metadata = self.service.plan_input_change(
            table_name="material_specs",
            field_name="Spec",
        )
        inventory = self.service.plan_input_change(
            table_name="inventory",
            field_name="Qty",
        )

        self.assertTrue(geometry.mark_dxf_binding_stale)
        self.assertTrue(geometry.invalidate_solver_results)
        self.assertFalse(metadata.mark_dxf_binding_stale)
        self.assertFalse(metadata.invalidate_solver_results)
        self.assertTrue(inventory.invalidate_solver_results)
        self.assertTrue(inventory.update_material_summary)


if __name__ == "__main__":
    unittest.main()
