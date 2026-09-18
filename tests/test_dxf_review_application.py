from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from dxf_import.models import (
    CoordinateSystem,
    DXFImportError,
    DXFImportResult,
    GeometryTolerances,
    Strut,
    Waler,
)
from dxf_import.review_workflow import DXFReviewWorkflow


def _member_values(identifier: str, handle: str) -> dict:
    return {
        "id": identifier,
        "start": (0.0, 0.0),
        "end": (1000.0, 0.0),
        "source_layer": "MEMBER",
        "source_handles": (handle,),
        "source_entity_types": ("LINE",),
        "recognition_method": "existing_centerline",
        "centerline_computed": False,
        "source_width": 300.0,
        "confidence": 1.0,
    }


def _result(path: Path, fingerprint: str = "ABC") -> DXFImportResult:
    waler = Waler(**_member_values("W1", "HW"))
    strut = Strut(
        **_member_values("S1", "HS"),
        from_waler="W1",
        to_waler="W1",
    )
    return DXFImportResult(
        source_path=str(path),
        source_fingerprint=fingerprint,
        layer_names=("MEMBER",),
        selected_layers={"waler": ("MEMBER",)},
        layer_info=(),
        walers=(waler,),
        struts=(strut,),
        braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={},
        layer_classification={"MEMBER": "waler"},
    )


class _Importer:
    def __init__(self, result: DXFImportResult):
        self.result = result
        self.source_fingerprint = result.source_fingerprint
        self.layer_names = result.layer_names
        self.tolerances = GeometryTolerances()
        self.convert_calls = []

    def convert(self, **kwargs):
        self.convert_calls.append(kwargs)
        return replace(
            self.result,
            layer_classification=dict(kwargs["layer_roles"]),
            excluded_sources=tuple(kwargs["excluded_sources"]),
            coordinate_system=kwargs["coordinate_system"],
        )


class DXFReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "review.dxf"
        self.path.write_bytes(b"workflow")
        self.result = _result(self.path)
        self.importer = _Importer(self.result)

    def tearDown(self):
        self.temp_dir.cleanup()

    def workflow(self, *, initial_world=True):
        return DXFReviewWorkflow(
            self.importer,
            self.path,
            initial_world_result=(self.result if initial_world else None),
            material_specs=(
                {"Usage": "圍令", "spec": "H400x400"},
                {"Usage": "支撐", "spec": "H400x400"},
            ),
        )

    def test_world_result_is_canonical_and_coordinate_result_is_derived(self):
        workflow = self.workflow()

        mutation = workflow.set_coordinate_origin((100.0, -50.0))

        self.assertTrue(mutation.changed)
        self.assertEqual(workflow.world_result.walers[0].start, (0.0, 0.0))
        self.assertEqual(workflow.result.walers[0].start, (-100.0, 50.0))
        self.assertEqual(
            workflow.result.coordinate_system,
            CoordinateSystem("local", 100.0, -50.0, "selected_candidate_point"),
        )

    def test_coordinate_mutation_rebuilds_review_and_reports_confirmation_loss(self):
        workflow = self.workflow()
        item = workflow.review_item_for_member("W1")
        self.assertIsNotNone(item)
        self.assertTrue(workflow.confirm(item))

        mutation = workflow.set_coordinate_origin((100.0, 200.0))

        self.assertEqual(mutation.invalidated_confirmations, ("W1",))
        self.assertFalse(
            workflow.is_review_item_confirmed(
                workflow.review_item_for_member("W1")
            )
        )

    def test_material_mutation_updates_world_and_local_projection_once(self):
        workflow = self.workflow()
        workflow.set_coordinate_origin((100.0, 0.0))

        mutation = workflow.set_material_spec("S1", "H400x400")

        self.assertTrue(mutation.changed)
        self.assertEqual(workflow.world_result.struts[0].material_spec, "H400x400")
        self.assertEqual(workflow.result.struts[0].material_spec, "H400x400")
        self.assertEqual(workflow.result.struts[0].start, (-100.0, 0.0))

    def test_initiating_member_confirmation_loss_is_not_reported_as_collateral(self):
        workflow = self.workflow()
        item = workflow.review_item_for_member("S1")
        self.assertTrue(workflow.confirm(item))

        mutation = workflow.set_material_spec("S1", "H400x400")

        self.assertEqual(mutation.invalidated_confirmations, ())
        self.assertFalse(
            workflow.is_review_item_confirmed(
                workflow.review_item_for_member("S1")
            )
        )

    def test_recognition_owns_replay_and_projection_sequence(self):
        workflow = self.workflow(initial_world=False)

        mutation = workflow.recognize({"MEMBER": "waler"})

        self.assertTrue(mutation.changed)
        self.assertEqual(len(self.importer.convert_calls), 1)
        self.assertEqual(workflow.world_result.coordinate_system, CoordinateSystem())
        self.assertEqual(workflow.result.layer_classification, {"MEMBER": "waler"})
        self.assertEqual(len(workflow.review_items), 2)

    def test_failed_normal_recognition_preserves_existing_clear_result_contract(self):
        workflow = self.workflow()
        self.importer.convert = lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("recognition failed")
        )

        with self.assertRaisesRegex(RuntimeError, "recognition failed"):
            workflow.recognize({"MEMBER": "waler"})

        self.assertIsNone(workflow.world_result)
        self.assertIsNone(workflow.result)
        self.assertEqual(workflow.review_items, ())

    def test_stale_exclusion_plan_cannot_overwrite_newer_review_state(self):
        workflow = self.workflow()
        plan = workflow.plan_source_exclusion_change(())
        workflow.set_coordinate_origin((25.0, 50.0))
        current_world = workflow.world_result

        with self.assertRaisesRegex(DXFImportError, "已變更"):
            workflow.commit_source_exclusion_plan(plan)

        self.assertIs(workflow.world_result, current_world)
        self.assertEqual(workflow.result.coordinate_system.mode, "local")

    def test_serialization_uses_owned_application_state(self):
        workflow = self.workflow()
        workflow.set_coordinate_origin((12.5, -8.0))
        workflow.set_import_mode("append")

        state = workflow.serialize_review_state(
            layer_roles={"MEMBER": "waler"},
        )

        self.assertEqual(state["review_state_version"], 2)
        self.assertEqual(state["coordinate_system"]["mode"], "local")
        self.assertEqual(state["coordinate_system"]["origin_x"], 12.5)
        self.assertEqual(state["import_mode"], "append")
        self.assertEqual(state["layer_classification"], {"MEMBER": "waler"})


if __name__ == "__main__":
    unittest.main()
