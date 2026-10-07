from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import dxf_import.corner_brace_repair as corner_brace_repair
from dxf_import.importer import DXFImporter
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import canonical_source_identity
from tests.sample_dxf_assets import Y05_DXF_PATH, Y29_DXF_PATH


PROJECT_CASES = Path(__file__).resolve().parents[1] / "project_cases"
Y05_PROJECT = PROJECT_CASES / "Y05車站第一層支撐" / "project.json"
Y29_PROJECT = PROJECT_CASES / "Y29車站第一層支撐" / "project.json"


def _review_state(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["dxf_import_state"]


def _workflow(path: Path, project_path: Path) -> DXFReviewWorkflow:
    state = _review_state(project_path)
    importer = DXFImporter(path).read()
    workflow = DXFReviewWorkflow(
        importer,
        path,
        initial_state=state,
        resume_review=True,
    )
    workflow.recognize(state["layer_classification"])
    return workflow


def _candidate_store_projection(plan):
    store = plan.candidate_point_store
    return tuple(
        (identifier, store.component_points(identifier))
        for identifier in store.component_ids()
    )


def _plan_projection(plan):
    return (
        plan.excluded_sources,
        plan.world_result,
        plan.result,
        plan.problem_records,
        plan.review_items,
        dict(plan.review_confirmations),
        _candidate_store_projection(plan),
        plan.manual_replay,
        plan.effects,
    )


@unittest.skipUnless(
    Y05_DXF_PATH.is_file() and Y05_PROJECT.is_file(),
    "Y05 DXF/project fixture unavailable",
)
class Y05SourceExclusionReplayRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = _workflow(Y05_DXF_PATH, Y05_PROJECT)

    def test_paired_joist_exclusion_matches_full_validation_oracle(self):
        workflow = self.workflow
        selected = next(
            item for item in workflow.review_items
            if item.display_id == "BM29" and "E91" in item.source_handles
        )

        optimized, restoring, identity = workflow.plan_source_exclusion_for_item(
            selected
        )
        with patch.object(
            corner_brace_repair,
            "_candidate_passes_existing_validation",
            side_effect=corner_brace_repair._candidate_passes_full_validation,
        ):
            canonical, canonical_restoring, canonical_identity = (
                workflow.plan_source_exclusion_for_item(selected)
            )

        self.assertFalse(restoring)
        self.assertEqual((restoring, identity), (canonical_restoring, canonical_identity))
        self.assertEqual(_plan_projection(optimized), _plan_projection(canonical))
        self.assertEqual(
            optimized.manual_replay.preserved,
            tuple(f"CB{number} CornerBrace repair" for number in range(66, 77)),
        )
        self.assertEqual(optimized.manual_replay.needs_review, ())
        self.assertEqual(optimized.manual_replay.disabled, ())
        self.assertEqual(
            [
                member.id
                for member in workflow.world_result.beams
                if "E91" in member.source_handles
            ],
            ["BM28", "BM29"],
        )
        self.assertFalse(
            any("E91" in member.source_handles for member in optimized.world_result.beams)
        )
        self.assertEqual(
            len(
                [
                    member
                    for member in optimized.world_result.corner_braces
                    if member.repair_provenance is not None
                ]
            ),
            11,
        )

    def test_s14_exclusion_replays_stable_references_and_same_target_entities(self):
        workflow = self.workflow
        selected = next(
            item
            for item in workflow.review_items
            if item.display_id == "S14" and "D1A" in item.source_handles
        )
        planned, restoring, identity = workflow.plan_source_exclusion_for_item(
            selected
        )
        with patch.object(
            corner_brace_repair,
            "_candidate_passes_existing_validation",
            side_effect=corner_brace_repair._candidate_passes_full_validation,
        ):
            canonical, canonical_restoring, canonical_identity = (
                workflow.plan_source_exclusion_for_item(selected)
            )

        self.assertFalse(restoring)
        self.assertEqual(identity, "strut:D1A")
        self.assertEqual(
            (restoring, identity),
            (canonical_restoring, canonical_identity),
        )
        self.assertEqual(_plan_projection(planned), _plan_projection(canonical))
        self.assertEqual(
            planned.manual_replay.preserved,
            tuple(f"CB{number} CornerBrace repair" for number in range(66, 77)),
        )
        self.assertEqual(planned.manual_replay.needs_review, ())
        self.assertEqual(planned.manual_replay.disabled, ())
        self.assertEqual(dict(workflow.review_confirmations), {})
        self.assertEqual(dict(planned.review_confirmations), {})
        removed_source_handles = {
            value.source_handles
            for value in workflow.world_result.corner_braces
            if value.id in {"CB28", "CB29", "CB30", "CB31"}
        }
        self.assertTrue(removed_source_handles)
        self.assertFalse(
            removed_source_handles.intersection(
                value.source_handles for value in planned.world_result.corner_braces
            )
        )

        before_corners = {
            value.id: value for value in workflow.world_result.corner_braces
        }
        after_corners = {
            value.id: value for value in planned.world_result.corner_braces
        }
        before_connections = {
            value.corner_brace_id: value
            for value in workflow.world_result.corner_brace_connections
        }
        after_connections = {
            value.corner_brace_id: value
            for value in planned.world_result.corner_brace_connections
        }
        before_walers = {value.id: value for value in workflow.world_result.walers}
        after_walers = {value.id: value for value in planned.world_result.walers}
        before_struts = {value.id: value for value in workflow.world_result.struts}
        after_struts = {value.id: value for value in planned.world_result.struts}

        expected_targets = {
            "CB66": ("W5", "W5", "waler:B29", "S5", "S5", "strut:B05"),
            "CB67": ("W6", "W6", "waler:B34", "S5", "S5", "strut:B05"),
            "CB68": ("W13", "W13", "waler:1647", "S21", "S20", "strut:D74"),
            "CB69": ("W13", "W13", "waler:1647", "S20", "S19", "strut:D4B"),
            "CB70": ("W13", "W13", "waler:1647", "S19", "S18", "strut:D34"),
        }
        expected_references = {
            "CB66": ("CB61", "CB57", ("11D0",)),
            "CB67": ("CB62", "CB58", ("1205",)),
            "CB68": ("CB56", "CB52", ("113F",)),
            "CB69": ("CB53", "CB49", ("1126",)),
            "CB70": ("CB50", "CB46", ("110D",)),
        }
        for corner_id, expected in expected_targets.items():
            before_connection = before_connections[corner_id]
            after_connection = after_connections[corner_id]
            actual = (
                before_connection.waler_id,
                after_connection.waler_id,
                canonical_source_identity(
                    "waler",
                    before_walers[before_connection.waler_id].source_handles,
                ),
                before_connection.strut_id,
                after_connection.strut_id,
                canonical_source_identity(
                    "strut",
                    before_struts[before_connection.strut_id].source_handles,
                ),
            )
            self.assertEqual(actual, expected)
            self.assertEqual(
                canonical_source_identity(
                    "waler",
                    after_walers[after_connection.waler_id].source_handles,
                ),
                expected[2],
            )
            self.assertEqual(
                canonical_source_identity(
                    "strut",
                    after_struts[after_connection.strut_id].source_handles,
                ),
                expected[5],
            )

            before_provenance = before_corners[corner_id].repair_provenance
            after_provenance = after_corners[corner_id].repair_provenance
            self.assertIsNotNone(before_provenance)
            self.assertIsNotNone(after_provenance)
            assert before_provenance is not None
            assert after_provenance is not None
            self.assertEqual(before_provenance.manual_secondary_references, ())
            self.assertEqual(
                (
                    before_provenance.selected_template_reference.member_id,
                    after_provenance.selected_template_reference.member_id,
                    before_provenance.selected_template_reference.subject_key.source_handles,
                ),
                expected_references[corner_id],
            )
            self.assertEqual(
                after_provenance.selected_template_reference.subject_key,
                before_provenance.selected_template_reference.subject_key,
            )

        reviewed_ids = {
            item.member_id
            for item in planned.review_items
            if item.role == "corner_brace" and item.status == "recognized"
        }
        self.assertTrue(set(range(66, 77)).issubset(
            {int(value[2:]) for value in reviewed_ids if value and value.startswith("CB")}
        ))

    def test_multi_pending_matches_same_final_canonical_exclusion_set(self):
        workflow = _workflow(Y05_DXF_PATH, Y05_PROJECT)
        paired_siblings = tuple(
            item
            for item in workflow.review_items
            if item.display_id in {"BM28", "BM29"}
            and "E91" in item.source_handles
        )
        self.assertEqual(len(paired_siblings), 2)
        strut = next(
            item
            for item in workflow.review_items
            if item.display_id == "S14" and "D1A" in item.source_handles
        )

        workflow.mark_source_exclusion(paired_siblings[0])
        workflow.mark_source_exclusion(paired_siblings[1])
        self.assertEqual(
            workflow.pending_source_exclusion_draft.identities,
            ("beam:E91",),
        )
        workflow.mark_source_exclusion(strut)
        draft = workflow.pending_source_exclusion_draft
        self.assertEqual(len(draft.sources), 2)

        pending_plan = workflow.plan_pending_source_exclusions()
        canonical_plan = workflow.plan_source_exclusion_change(
            (*workflow.excluded_sources, *draft.sources)
        )

        self.assertEqual(_plan_projection(pending_plan), _plan_projection(canonical_plan))
        self.assertEqual(pending_plan.manual_replay.preserved, canonical_plan.manual_replay.preserved)
        self.assertEqual(pending_plan.manual_replay.needs_review, ())
        self.assertEqual(pending_plan.manual_replay.disabled, ())
        self.assertEqual(
            {
                member.id: member.repair_provenance
                for member in pending_plan.world_result.corner_braces
                if member.repair_provenance is not None
            },
            {
                member.id: member.repair_provenance
                for member in canonical_plan.world_result.corner_braces
                if member.repair_provenance is not None
            },
        )


@unittest.skipUnless(
    Y29_DXF_PATH.is_file() and Y29_PROJECT.is_file(),
    "Y29 DXF/project fixture unavailable",
)
class Y29SourceExclusionReplayRegressionTests(unittest.TestCase):
    def test_manual_waler_exclude_pause_resume_and_restore(self):
        workflow = _workflow(Y29_DXF_PATH, Y29_PROJECT)
        selected = next(
            item for item in workflow.review_items
            if item.role == "waler" and "58D" in item.source_handles
        )
        plan, restoring, identity = workflow.plan_source_exclusion_for_item(selected)
        self.assertFalse(restoring)
        workflow.commit_source_exclusion_plan(plan)
        self.assertIn("W11 人工正式工程線", workflow.last_manual_replay_report.disabled)

        saved = workflow.serialize_review_state(
            layer_roles=workflow.world_result.layer_classification,
        )
        resumed_importer = DXFImporter(Y29_DXF_PATH).read()
        resumed = DXFReviewWorkflow(
            resumed_importer,
            Y29_DXF_PATH,
            initial_state=saved,
            resume_review=True,
        )
        resumed.recognize(saved["layer_classification"])
        excluded = resumed.review_item_for_identity(
            resumed.review_items,
            identity,
            excluded=True,
        )
        self.assertIsNotNone(excluded)
        restore, restoring, restored_identity = resumed.plan_source_exclusion_for_item(
            excluded
        )
        self.assertTrue(restoring)
        self.assertEqual(restored_identity, identity)
        resumed.commit_source_exclusion_plan(restore)

        restored = next(
            member for member in resumed.world_result.walers
            if "58D" in member.source_handles
        )
        self.assertEqual(restored.engineering_line_authority, "manual_repair")
        self.assertIn(
            "W11 人工正式工程線",
            resumed.last_manual_replay_report.preserved,
        )

    def test_multi_pending_round_trip_and_single_restore_stay_canonical(self):
        workflow = _workflow(Y29_DXF_PATH, Y29_PROJECT)
        selected = tuple(
            next(
                item
                for item in workflow.review_items
                if item.display_id == display_id and handle in item.source_handles
            )
            for display_id, handle in (("W11", "58D"), ("S1", "D7"))
        )
        for item in selected:
            workflow.mark_source_exclusion(item)
        draft = workflow.pending_source_exclusion_draft
        pending_plan = workflow.plan_pending_source_exclusions()
        canonical_plan = workflow.plan_source_exclusion_change(
            (*workflow.excluded_sources, *draft.sources)
        )
        self.assertEqual(_plan_projection(pending_plan), _plan_projection(canonical_plan))
        workflow.commit_source_exclusion_plan(pending_plan)

        saved = workflow.serialize_review_state(
            layer_roles=workflow.world_result.layer_classification,
        )
        self.assertNotIn("pending_source_exclusion", saved)
        resumed_importer = DXFImporter(Y29_DXF_PATH).read()
        resumed = DXFReviewWorkflow(
            resumed_importer,
            Y29_DXF_PATH,
            initial_state=saved,
            resume_review=True,
        )
        resumed.recognize(saved["layer_classification"])
        self.assertEqual(
            {source.identity for source in resumed.excluded_sources},
            {source.identity for source in pending_plan.excluded_sources},
        )
        waler_identity = canonical_source_identity("waler", ("58D",))
        excluded_waler = resumed.review_item_for_identity(
            resumed.review_items,
            waler_identity,
            excluded=True,
        )
        self.assertIsNotNone(excluded_waler)
        restore, restoring, identity = resumed.plan_source_exclusion_for_item(
            excluded_waler
        )
        self.assertTrue(restoring)
        self.assertEqual(identity, waler_identity)
        resumed.commit_source_exclusion_plan(restore)
        restored = next(
            member
            for member in resumed.world_result.walers
            if "58D" in member.source_handles
        )
        self.assertEqual(restored.engineering_line_authority, "manual_repair")


if __name__ == "__main__":
    unittest.main()
