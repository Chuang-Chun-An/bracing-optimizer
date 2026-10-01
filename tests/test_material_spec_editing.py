import copy
import unittest

from bracing_optimizer.application.material_spec_editing import (
    MaterialSpecEditError,
    MaterialSpecEditOperation,
    MaterialSpecEditRequest,
    MaterialSpecEditStatus,
    MaterialSpecEditing,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_results import ProjectResultModel
from bracing_optimizer.application.project_service import ProjectService


class MaterialSpecEditingTests(unittest.TestCase):
    @staticmethod
    def model() -> ProjectDataModel:
        return ProjectDataModel(
            walers=[{"WalerID": "W1", "material_spec": "H350x350"}],
            struts=[{"StrutID": "S1", "material_spec": "H350x350"}],
            inventory=[
                {
                    "ItemCode": "S1",
                    "Usage": "支撐",
                    "Spec": "H350x350",
                    "Length": 4500,
                    "Qty": 1,
                },
                {
                    "ItemCode": "W1",
                    "Usage": "圍令",
                    "Spec": "H350x350",
                    "Length": 8000,
                    "Qty": 1,
                },
            ],
            material_specs=[
                {"Usage": "支撐", "Spec": "H350x350"},
                {"Usage": "圍令", "Spec": "H350x350"},
                {"Usage": "支撐", "Spec": "H500x500"},
            ],
        )

    @staticmethod
    def results() -> ProjectResultModel:
        return ProjectResultModel(
            result_items={"existing": {"type": "waler", "result": {}}},
            last_calculated_time="2026-10-01T12:00:00",
            persisted_payload={"best_solution": {"result_items": []}},
        )

    def setUp(self):
        self.editing = MaterialSpecEditing(ProjectService.plan_input_change)

    @staticmethod
    def edit_request(
        *,
        index=1,
        usage="支撐",
        spec="H350x350",
        field="Spec",
        value="H350x350A",
        confirmed=False,
        expected_references=None,
    ):
        return MaterialSpecEditRequest(
            operation=MaterialSpecEditOperation.EDIT,
            row_index=index,
            expected_usage=usage,
            expected_spec=spec,
            field_name=field,
            proposed_value=value,
            allow_reference_sync=confirmed,
            expected_references=expected_references,
        )

    def test_reference_lookup_is_case_insensitive_whitespace_tolerant_and_scoped(self):
        model = self.model()
        model.inventory[0]["Spec"] = " h350X350 "
        summary = self.editing._references(model, " 支撐 ", "H350x350")
        self.assertEqual(summary.inventory, (0,))
        self.assertEqual(summary.struts, (0,))
        self.assertEqual(summary.walers, ())
        self.assertEqual(summary.count, 2)

    def test_no_op_and_defensive_request_failures_are_structured(self):
        model = self.model()
        results = self.results()
        no_op = self.editing.stage(
            model,
            results,
            self.edit_request(value="H350x350"),
        )
        invalid = self.editing.stage(
            model,
            results,
            self.edit_request(index=99),
        )
        stale = self.editing.stage(
            model,
            results,
            self.edit_request(spec="old"),
        )
        invalid_field = self.editing.stage(
            model,
            results,
            self.edit_request(field="Length"),
        )
        self.assertEqual(no_op.status, MaterialSpecEditStatus.NO_OP)
        self.assertEqual(invalid.error_code, MaterialSpecEditError.INVALID_ROW)
        self.assertEqual(stale.error_code, MaterialSpecEditError.STALE_REQUEST)
        self.assertEqual(invalid_field.error_code, MaterialSpecEditError.INVALID_FIELD)

    def test_required_rc_edit_and_delete_are_rejected(self):
        model = self.model()
        results = self.results()
        edit = self.editing.stage(
            model,
            results,
            self.edit_request(
                index=0,
                usage="圍令",
                spec="RC",
                value="RC2",
            ),
        )
        delete = self.editing.stage(
            model,
            results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.DELETE,
                row_index=0,
                expected_usage="圍令",
                expected_spec="RC",
            ),
        )
        self.assertEqual(edit.error_code, MaterialSpecEditError.REQUIRED_SPEC_LOCKED)
        self.assertEqual(delete.error_code, MaterialSpecEditError.REQUIRED_SPEC_LOCKED)

    def test_blank_duplicate_referenced_usage_and_delete_are_rejected(self):
        model = self.model()
        results = self.results()
        blank = self.editing.stage(
            model,
            results,
            self.edit_request(value=""),
        )
        duplicate = self.editing.stage(
            model,
            results,
            self.edit_request(index=3, spec="H500x500", value="H350x350"),
        )
        usage = self.editing.stage(
            model,
            results,
            self.edit_request(field="Usage", value="圍令"),
        )
        delete = self.editing.stage(
            model,
            results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.DELETE,
                row_index=1,
                expected_usage="支撐",
                expected_spec="H350x350",
            ),
        )
        self.assertEqual(blank.error_code, MaterialSpecEditError.BLANK_SPEC)
        self.assertEqual(duplicate.error_code, MaterialSpecEditError.DUPLICATE_SPEC)
        self.assertEqual(usage.error_code, MaterialSpecEditError.DUPLICATE_SPEC)
        self.assertEqual(delete.error_code, MaterialSpecEditError.REFERENCED_DELETE_BLOCKED)

        model.material_specs.pop(2)
        usage = self.editing.stage(
            model,
            results,
            self.edit_request(field="Usage", value="圍令"),
        )
        self.assertEqual(usage.error_code, MaterialSpecEditError.REFERENCED_USAGE_LOCKED)

    def test_referenced_rename_requires_confirmation_then_synchronizes_same_usage(self):
        model = self.model()
        results = self.results()
        request = self.edit_request()
        first = self.editing.stage(model, results, request)
        self.assertEqual(first.status, MaterialSpecEditStatus.CONFIRMATION_REQUIRED)
        self.assertEqual(first.references.inventory, (0,))
        self.assertEqual(first.references.struts, (0,))

        confirmed = self.editing.stage(
            model,
            results,
            self.edit_request(
                confirmed=True,
                expected_references=first.references,
            ),
        )
        self.assertEqual(confirmed.status, MaterialSpecEditStatus.STAGED)
        self.assertEqual(confirmed.project_data.material_specs[1]["Spec"], "H350x350A")
        self.assertEqual(confirmed.project_data.inventory[0]["Spec"], "H350x350A")
        self.assertEqual(confirmed.project_data.struts[0]["material_spec"], "H350x350A")
        self.assertEqual(confirmed.project_data.inventory[1]["Spec"], "H350x350")
        self.assertEqual(confirmed.project_data.walers[0]["material_spec"], "H350x350")

    def test_confirmed_rename_rejects_changed_row_or_reference_set(self):
        model = self.model()
        results = self.results()
        first = self.editing.stage(model, results, self.edit_request())

        changed_row = copy.deepcopy(model)
        changed_row.material_specs[1]["Spec"] = "changed"
        stale_row = self.editing.stage(
            changed_row,
            results,
            self.edit_request(
                confirmed=True,
                expected_references=first.references,
            ),
        )

        changed_references = copy.deepcopy(model)
        changed_references.struts.append(
            {"StrutID": "S2", "material_spec": "H350x350"}
        )
        stale_references = self.editing.stage(
            changed_references,
            results,
            self.edit_request(
                confirmed=True,
                expected_references=first.references,
            ),
        )
        self.assertEqual(stale_row.error_code, MaterialSpecEditError.STALE_REQUEST)
        self.assertEqual(
            stale_references.error_code,
            MaterialSpecEditError.STALE_REQUEST,
        )

    def test_result_lifecycle_and_dirty_effects_match_existing_policy(self):
        model = self.model()
        results = self.results()
        first = self.editing.stage(model, results, self.edit_request())
        renamed = self.editing.stage(
            model,
            results,
            self.edit_request(
                confirmed=True,
                expected_references=first.references,
            ),
        )
        self.assertEqual(renamed.project_results.result_items, {})
        self.assertTrue(renamed.clear_solver_memory)
        self.assertTrue(renamed.clear_support_candidate_cache)
        self.assertTrue(renamed.update_material_summary)
        self.assertEqual(renamed.dirty_reason, "輸入資料已變更")

        edited = self.editing.stage(
            model,
            results,
            self.edit_request(
                index=3,
                spec="H500x500",
                value="H500x500A",
            ),
        )
        deleted = self.editing.stage(
            model,
            results,
            MaterialSpecEditRequest(
                operation=MaterialSpecEditOperation.DELETE,
                row_index=3,
                expected_usage="支撐",
                expected_spec="H500x500",
            ),
        )
        for outcome in (edited, deleted):
            self.assertEqual(outcome.status, MaterialSpecEditStatus.STAGED)
            self.assertEqual(outcome.project_results, results)
            self.assertIsNot(outcome.project_results, results)
            self.assertFalse(outcome.clear_solver_memory)
            self.assertFalse(outcome.clear_support_candidate_cache)
            self.assertEqual(outcome.dirty_reason, "輸入資料已變更")

    def test_clone_preserves_all_runtime_state_before_mutation(self):
        model = self.model()
        model.dxf_binding = {"stale": False, "handles": ["A1"]}
        model.member_source_info = {"W1": {"layer": "WALER"}}
        model.walers[0]["runtime_source"] = {"handle": "A1"}

        staged = self.editing.clone_project_data(model)

        self.assertEqual(staged.__dict__, model.__dict__)
        self.assertIsNot(staged, model)
        self.assertIsNot(staged.dxf_binding, model.dxf_binding)
        self.assertIsNot(staged.member_source_info, model.member_source_info)
        self.assertIsNot(staged.walers, model.walers)
        self.assertIsNot(staged.walers[0]["runtime_source"], model.walers[0]["runtime_source"])

    def test_rejected_confirmation_no_op_and_copy_failure_leave_live_models_unchanged(self):
        class Uncopyable:
            def __deepcopy__(self, _memo):
                raise RuntimeError("cannot copy")

        model = self.model()
        results = self.results()
        original_data = copy.deepcopy(model.__dict__)
        original_results = copy.deepcopy(results)
        outcomes = (
            self.editing.stage(model, results, self.edit_request(index=99)),
            self.editing.stage(model, results, self.edit_request()),
            self.editing.stage(model, results, self.edit_request(value="H350x350")),
        )
        self.assertEqual(
            tuple(outcome.status for outcome in outcomes),
            (
                MaterialSpecEditStatus.REJECTED,
                MaterialSpecEditStatus.CONFIRMATION_REQUIRED,
                MaterialSpecEditStatus.NO_OP,
            ),
        )
        self.assertEqual(model.__dict__, original_data)
        self.assertEqual(results, original_results)

        model.runtime_only = Uncopyable()
        tables_before = model.to_case_data()
        with self.assertRaisesRegex(RuntimeError, "cannot copy"):
            self.editing.stage(
                model,
                results,
                self.edit_request(
                    index=3,
                    spec="H500x500",
                    value="H500x500A",
                ),
            )
        self.assertEqual(model.to_case_data(), tables_before)
        self.assertEqual(results, original_results)


if __name__ == "__main__":
    unittest.main()
