import json
import tempfile
import unittest
from pathlib import Path

import ezdxf

from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfStatus,
    ProjectPersistenceError,
)
from bracing_optimizer.application.project_service import (
    ProjectService,
    RelinkDxfRequest,
    SaveProjectRequest,
)


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


if __name__ == "__main__":
    unittest.main()
