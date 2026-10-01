import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from bracing_optimizer.infrastructure.project_persistence import (
    DxfAssetManager,
    DxfStatus,
    DxfWorkflowStatus,
    ProjectPersistenceError,
    PROJECT_SCHEMA_UNREADABLE_STAGE,
    ProjectSerializer,
)
from bracing_optimizer.application.project_data import TABLE_COLUMNS, ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import (
    ApplyDxfReviewRequest,
    BuildProjectPayloadRequest,
    PausedReviewRelinkRequest,
    PausedReviewRelinkStatus,
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


class FakeRecoveryStage:
    def __init__(
        self,
        candidate_path,
        candidate_fingerprint,
        base_state_token,
        recovered_state,
        world_result,
    ):
        self.candidate_path = Path(candidate_path).resolve()
        self.candidate_fingerprint = candidate_fingerprint
        self.base_state_token = base_state_token
        self._recovered_state = copy.deepcopy(recovered_state)
        self.world_result = world_result

    def copy_recovered_state(self):
        return copy.deepcopy(self._recovered_state)


class FakeRecoveryPlanner:
    def __init__(self, status="COMPATIBLE_RECOVERY_AVAILABLE"):
        self.status = status
        self.calls = []
        self.world_result = object()
        self.summary = SimpleNamespace(name="recovery-summary")

    def plan(
        self,
        candidate_path,
        candidate_fingerprint,
        saved_state,
        base_state_token,
        *,
        material_specs=(),
    ):
        self.calls.append((
            Path(candidate_path).resolve(),
            candidate_fingerprint,
            copy.deepcopy(saved_state),
            base_state_token,
            tuple(material_specs),
        ))
        if self.status != "COMPATIBLE_RECOVERY_AVAILABLE":
            return SimpleNamespace(
                status=self.status,
                plan=None,
                summary=self.summary,
                detail_lines=("planner detail",),
            )
        recovered = copy.deepcopy(saved_state)
        recovered["source_path"] = str(Path(candidate_path).resolve())
        recovered["source_fingerprint"] = candidate_fingerprint
        stage = FakeRecoveryStage(
            candidate_path,
            candidate_fingerprint,
            base_state_token,
            recovered,
            self.world_result,
        )
        return SimpleNamespace(
            status=self.status,
            plan=SimpleNamespace(stage=stage),
            summary=self.summary,
            detail_lines=(),
        )


class FailingRelinkReportManager(DxfAssetManager):
    def accepted_relink_report(self, source_path, *, summary):
        raise ProjectPersistenceError("狀態建立失敗", "simulated")


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


def create_dxf(path: Path, *, offset: float = 0.0) -> Path:
    document = ezdxf.new("R2010")
    document.modelspace().add_line((offset, 0), (offset + 1000, 0))
    document.saveas(path)
    return path


def paused_review_state(path: Path, **updates) -> dict:
    state = {
        "review_state_version": 2,
        "source_path": str(path),
        "source_fingerprint": DxfAssetManager.file_info(path).sha256.upper(),
        "layer_classification": {"0": "ignore"},
        "coordinate_system": {
            "mode": "local",
            "origin_x": 125.0,
            "origin_y": -75.0,
        },
        "import_mode": "replace",
        "excluded_sources": [{"role": "beam", "source_handles": ["6EF"]}],
        "manual_overrides": [{"role": "waler", "source_handles": ["10"]}],
        "double_support_decisions": [{"source": "S1|S2", "accepted": True}],
        "review_confirmations": {"waler:10": "ABC123"},
        "validation_messages": [{"severity": "warning", "code": "PENDING"}],
    }
    state.update(updates)
    return state


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

    def test_load_project_rejects_invalid_schema_versions_before_structure(self):
        invalid_versions = ("3", 3.0, True, False, None, 0, -1)

        for index, version in enumerate(invalid_versions):
            with self.subTest(version=version, value_type=type(version).__name__):
                path = self.root / f"invalid-version-{index}.json"
                saved_payload = project_payload(include_asset=False)
                saved_payload["schema_version"] = version
                path.write_text(json.dumps(saved_payload), encoding="utf-8")

                with self.assertRaises(ProjectPersistenceError) as raised:
                    self.service.load_project(path)

                self.assertIn("schema_version", raised.exception.stage)

    def test_load_project_rejects_future_version_before_structure_validation(self):
        path = self.root / "future.json"
        saved_payload = project_payload(include_asset=False)
        saved_payload["schema_version"] = 4
        path.write_text(json.dumps(saved_payload), encoding="utf-8")

        with self.assertRaises(ProjectPersistenceError) as raised:
            self.service.load_project(path)

        self.assertIn("版本不相容", raised.exception.stage)
        self.assertIn("較新程式", raised.exception.detail)
        self.assertNotIn("dxf_asset", raised.exception.detail)

    def test_load_project_reports_neutral_error_for_unreadable_compatible_version(self):
        for version in (2, None):
            with self.subTest(version=version):
                path = self.root / f"unreadable-{version}.json"
                saved_payload = project_payload(include_asset=False)
                if version is None:
                    saved_payload.pop("schema_version")
                else:
                    saved_payload["schema_version"] = version
                path.write_text(json.dumps(saved_payload), encoding="utf-8")

                with self.assertRaises(ProjectPersistenceError) as raised:
                    self.service.load_project(path)

                self.assertIn("無法以現行格式讀取", raised.exception.stage)
                self.assertIn("dxf_asset", raised.exception.detail)

    def test_load_project_keeps_current_version_validation_error(self):
        path = self.root / "invalid-current.json"
        path.write_text(
            json.dumps(project_payload(include_asset=False)),
            encoding="utf-8",
        )

        with self.assertRaises(ProjectPersistenceError) as raised:
            self.service.load_project(path)

        self.assertEqual(raised.exception.stage, "JSON 驗證失敗")
        self.assertIn("dxf_asset", raised.exception.detail)

    def test_load_project_rejects_current_row_schema_mismatch_before_hydration(self):
        path = self.root / "invalid-current-row.json"
        saved_payload = project_payload()
        saved_payload["input_data"] = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
            }],
        ).to_case_data()
        saved_payload["input_data"]["walers"][0].pop("Remark")
        path.write_text(json.dumps(saved_payload), encoding="utf-8")

        with self.assertRaises(ProjectPersistenceError) as raised:
            self.service.load_project(path)

        self.assertEqual(raised.exception.stage, PROJECT_SCHEMA_UNREADABLE_STAGE)
        self.assertIn("底層驗證錯誤", raised.exception.detail)
        self.assertIn("input_data.walers[1]", raised.exception.detail)
        self.assertIn("Remark", raised.exception.detail)

    def test_compatible_version_is_rewritten_only_by_actual_save(self):
        for version in (2, None):
            with self.subTest(version=version):
                path = self.root / f"save-compatible-{version}.json"
                saved_payload = project_payload()
                if version is None:
                    saved_payload.pop("schema_version")
                else:
                    saved_payload["schema_version"] = version
                original_text = json.dumps(saved_payload, ensure_ascii=False)
                path.write_text(original_text, encoding="utf-8")

                loaded = self.service.load_project(path)

                self.assertEqual(path.read_text(encoding="utf-8"), original_text)

                self.service.save_project(
                    SaveProjectRequest(
                        project_path=path,
                        payload=loaded.payload,
                        current_project_path=path,
                        existing_asset=loaded.payload.get("dxf_asset"),
                        import_state=loaded.payload.get("dxf_import_state"),
                        current_dxf_report=loaded.dxf_status_report,
                        has_solver_result=False,
                    )
                )

                persisted = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(persisted["schema_version"], 3)
                ProjectSerializer.validate(persisted)

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

    def test_paused_review_exact_relink_stages_only_source_reference_changes(self):
        source = create_dxf(self.root / "original.dxf")
        candidate = self.root / "renamed.dxf"
        shutil.copy2(source, candidate)
        saved_state = paused_review_state(source)
        before = copy.deepcopy(saved_state)
        planner = FakeRecoveryPlanner()
        service = ProjectService(paused_review_recovery_planner=planner)

        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        self.assertEqual(evaluation.status, PausedReviewRelinkStatus.EXACT_MATCH)
        self.assertIsNotNone(evaluation.plan)
        expected = copy.deepcopy(before)
        expected["source_path"] = str(candidate.resolve())
        expected["source_fingerprint"] = before["source_fingerprint"].upper()
        self.assertEqual(evaluation.plan.relinked_state, expected)
        self.assertEqual(saved_state, before)
        self.assertIsNot(evaluation.plan.relinked_state, saved_state)
        self.assertIsNot(
            evaluation.plan.relinked_state["excluded_sources"],
            saved_state["excluded_sources"],
        )
        self.assertEqual(planner.calls, [])
        self.assertIsNone(evaluation.recovery_seed)
        self.assertIsNone(evaluation.recovery_summary)

    def test_paused_review_relink_reports_incompatible_planner_result(self):
        source = create_dxf(self.root / "original.dxf")
        candidate = create_dxf(self.root / "changed.dxf", offset=5000)
        saved_state = paused_review_state(source)
        before = copy.deepcopy(saved_state)
        planner = FakeRecoveryPlanner("INCOMPATIBLE_SOURCE")
        service = ProjectService(paused_review_recovery_planner=planner)

        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        self.assertEqual(
            evaluation.status,
            PausedReviewRelinkStatus.INCOMPATIBLE_SOURCE,
        )
        self.assertIsNone(evaluation.plan)
        self.assertIsNotNone(evaluation.recovery_seed)
        self.assertIs(evaluation.recovery_summary, planner.summary)
        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(saved_state, before)

    def test_paused_review_relink_returns_compatible_recovery_plan(self):
        source = create_dxf(self.root / "original.dxf")
        candidate = create_dxf(self.root / "changed.dxf", offset=5000)
        saved_state = paused_review_state(source)
        planner = FakeRecoveryPlanner()
        service = ProjectService(paused_review_recovery_planner=planner)

        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
                material_specs=({"Usage": "圍令", "Spec": "H350"},),
            )
        )

        self.assertEqual(
            evaluation.status,
            PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertIsNotNone(evaluation.plan)
        self.assertEqual(
            evaluation.plan.status,
            PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertIs(evaluation.plan.candidate_world_result, planner.world_result)
        self.assertIs(evaluation.recovery_summary, planner.summary)
        self.assertEqual(
            planner.calls[0][4],
            ({"Usage": "圍令", "Spec": "H350"},),
        )
        self.assertEqual(saved_state["source_path"], str(source))

    def test_paused_review_relink_maps_planner_validation_failure(self):
        source = create_dxf(self.root / "original.dxf")
        candidate = create_dxf(self.root / "changed.dxf", offset=5000)
        planner = FakeRecoveryPlanner("VALIDATION_FAILED")
        service = ProjectService(paused_review_recovery_planner=planner)

        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=paused_review_state(source),
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        self.assertEqual(
            evaluation.status,
            PausedReviewRelinkStatus.VALIDATION_FAILED,
        )
        self.assertIsNone(evaluation.plan)
        self.assertEqual(evaluation.detail_lines, ("planner detail",))

    def test_paused_review_relink_reports_invalid_candidate(self):
        source = create_dxf(self.root / "original.dxf")
        candidate = self.root / "invalid.dxf"
        candidate.write_text("not a dxf", encoding="utf-8")

        evaluation = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=paused_review_state(source),
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        self.assertEqual(
            evaluation.status,
            PausedReviewRelinkStatus.VALIDATION_FAILED,
        )
        self.assertIsNone(evaluation.plan)
        self.assertTrue(evaluation.detail_lines)

    def test_paused_review_relink_requires_saved_fingerprint_and_review_status(self):
        candidate = create_dxf(self.root / "candidate.dxf")
        no_fingerprint = {"source_path": "old.dxf"}

        missing = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=no_fingerprint,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        wrong_workflow = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=paused_review_state(candidate),
                workflow_status=DxfWorkflowStatus.COMPLETED,
            )
        )

        self.assertEqual(
            missing.status,
            PausedReviewRelinkStatus.VALIDATION_FAILED,
        )
        self.assertEqual(
            wrong_workflow.status,
            PausedReviewRelinkStatus.VALIDATION_FAILED,
        )
        self.assertIsNone(missing.plan)
        self.assertIsNone(wrong_workflow.plan)

    def test_paused_review_relink_commit_revalidates_candidate(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = self.root / "candidate.dxf"
        shutil.copy2(source, candidate)
        saved_state = paused_review_state(source)
        evaluation = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        create_dxf(candidate, offset=9000)

        committed = self.service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=saved_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertFalse(committed.accepted)
        self.assertEqual(
            committed.status,
            PausedReviewRelinkStatus.VALIDATION_FAILED,
        )
        self.assertIsNone(committed.relinked_state)
        self.assertIsNone(committed.dxf_status_report)

    def test_paused_review_relink_commit_rejects_stale_review_state(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = self.root / "candidate.dxf"
        shutil.copy2(source, candidate)
        saved_state = paused_review_state(source)
        evaluation = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        changed_state = copy.deepcopy(saved_state)
        changed_state["review_confirmations"]["strut:20"] = "NEW"

        committed = self.service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=changed_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertFalse(committed.accepted)
        self.assertIsNone(committed.relinked_state)
        self.assertIsNone(committed.dxf_status_report)
        self.assertEqual(changed_state["source_path"], str(source))

    def test_paused_review_exact_commit_returns_pending_save_adoption(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = self.root / "candidate.dxf"
        shutil.copy2(source, candidate)
        saved_state = paused_review_state(source)
        evaluation = self.service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        committed = self.service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=saved_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertTrue(committed.accepted)
        self.assertEqual(committed.status, PausedReviewRelinkStatus.EXACT_MATCH)
        self.assertEqual(committed.workflow_status, DxfWorkflowStatus.REVIEW)
        self.assertEqual(
            committed.dxf_status_report.status,
            DxfStatus.VERIFIED_PENDING_SAVE,
        )
        self.assertEqual(
            committed.relinked_state["source_path"],
            str(candidate.resolve()),
        )
        self.assertEqual(saved_state["source_path"], str(source))
        self.assertIsNot(committed.relinked_state, evaluation.plan.relinked_state)

    def test_paused_review_compatible_commit_returns_candidate_adoption(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = create_dxf(self.root / "candidate.dxf", offset=5000)
        saved_state = paused_review_state(source)
        planner = FakeRecoveryPlanner()
        service = ProjectService(paused_review_recovery_planner=planner)
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=saved_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertTrue(committed.accepted)
        self.assertEqual(
            committed.status,
            PausedReviewRelinkStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertEqual(committed.workflow_status, DxfWorkflowStatus.REVIEW)
        self.assertIs(committed.candidate_world_result, planner.world_result)
        self.assertIs(committed.recovery_summary, planner.summary)
        self.assertEqual(
            committed.relinked_state["source_path"],
            str(candidate.resolve()),
        )
        self.assertEqual(saved_state["source_path"], str(source))

    def test_paused_review_compatible_commit_rejects_changed_candidate(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = create_dxf(self.root / "candidate.dxf", offset=5000)
        saved_state = paused_review_state(source)
        planner = FakeRecoveryPlanner()
        service = ProjectService(paused_review_recovery_planner=planner)
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        create_dxf(candidate, offset=9000)

        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=saved_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertFalse(committed.accepted)
        self.assertIsNone(committed.relinked_state)
        self.assertIsNone(committed.candidate_world_result)

    def test_paused_review_compatible_commit_rejects_stale_review_state(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = create_dxf(self.root / "candidate.dxf", offset=5000)
        saved_state = paused_review_state(source)
        planner = FakeRecoveryPlanner()
        service = ProjectService(paused_review_recovery_planner=planner)
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )
        changed_state = copy.deepcopy(saved_state)
        changed_state["import_mode"] = "append"

        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=changed_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertFalse(committed.accepted)
        self.assertIsNone(committed.relinked_state)
        self.assertEqual(changed_state["source_path"], str(source))

    def test_paused_review_compatible_commit_rejects_status_creation_failure(self):
        source = create_dxf(self.root / "source.dxf")
        candidate = create_dxf(self.root / "candidate.dxf", offset=5000)
        saved_state = paused_review_state(source)
        planner = FakeRecoveryPlanner()
        service = ProjectService(
            FailingRelinkReportManager(),
            paused_review_recovery_planner=planner,
        )
        evaluation = service.evaluate_paused_review_relink(
            PausedReviewRelinkRequest(
                candidate_path=candidate,
                saved_state=saved_state,
                workflow_status=DxfWorkflowStatus.REVIEW,
            )
        )

        committed = service.commit_paused_review_relink(
            evaluation.plan,
            current_saved_state=saved_state,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
        )

        self.assertFalse(committed.accepted)
        self.assertIsNone(committed.relinked_state)
        self.assertIsNone(committed.dxf_status_report)
        self.assertIsNone(committed.candidate_world_result)

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
