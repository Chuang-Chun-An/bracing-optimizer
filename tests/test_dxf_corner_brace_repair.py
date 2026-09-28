from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from dxf_import.corner_brace_repair import (
    PRIMARY_REFERENCE,
    SECONDARY_REFERENCE,
    apply_corner_brace_repair,
    eligible_repair_references,
    plan_corner_brace_repair,
    repair_subject_key,
    residual_axis_hypotheses,
    target_residual_segments,
)
from dxf_import.models import (
    CornerBrace,
    CornerBraceRepairProvenance,
    CornerBraceRepairReference,
    CornerBraceRepairSubjectKey,
    CandidatePoint,
    DXFImportResult,
    ExcludedSource,
    GeometryTolerances,
    ReviewItem,
    SourceGeometry,
    Strut,
    ValidationMessage,
    Waler,
)
from dxf_import.review_confirmation import confirm_review_item
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.review_recovery import RecoveryCategory, RecoverySummary
from dxf_import.review_recovery_planner import ReviewRecoveryPlanner
from dxf_import.source_exclusion import (
    capture_manual_overrides,
    manual_override_from_mapping,
    replay_manual_overrides,
)
from dxf_import.validation import build_problem_records, build_review_items
from dxf_import.waler_contact_adjustment import (
    build_corner_brace_connections,
    initialize_waler_contact_review,
)


def _waler(identifier: str, x: float) -> Waler:
    return Waler(
        identifier,
        (x, -1000.0),
        (x, 5000.0),
        "WALER",
        (f"W-{identifier}",),
        ("LINE",),
        "existing_centerline",
        False,
        400.0,
        1.0,
    )


def _strut(identifier: str, y: float, width: float = 400.0) -> Strut:
    return Strut(
        identifier,
        (0.0, y),
        (5000.0, y),
        "STRUT",
        (f"S-{identifier}",),
        ("LINE",),
        "existing_centerline",
        False,
        width,
        "W1",
        "W2",
        1.0,
    )


def _corner(
    identifier: str,
    start: tuple[float, float],
    end: tuple[float, float],
    handle: str,
    *,
    selection_source: str = "auto",
    provenance: CornerBraceRepairProvenance | None = None,
) -> CornerBrace:
    return CornerBrace(
        identifier,
        start,
        end,
        "CORNER",
        (handle,),
        ("INSERT",),
        "brace_centerline_intersections",
        True,
        0.0,
        1.0,
        selection_source=selection_source,
        repair_provenance=provenance,
    )


def _result(
    *,
    target_kind: str = "recognized",
    target_residual: bool = True,
    include_primary: bool = True,
    strut_width: float = 400.0,
) -> tuple[DXFImportResult, ReviewItem]:
    walers = (_waler("W1", 0.0), _waler("W2", 5000.0))
    struts = (_strut("S1", 0.0, strut_width), _strut("S2", 3000.0, strut_width))
    corners = []
    if target_kind == "recognized":
        # Deliberately wrong CB71-like baseline; residual source points to the
        # desired 45-degree engineering axis.
        corners.append(_corner("CB71", (0.0, 800.0), (800.0, 0.0), "T1"))
    if include_primary:
        corners.append(_corner("CB10", (0.0, 4000.0), (1000.0, 3000.0), "P1"))
    geometry = ()
    if target_residual:
        geometry = (
            SourceGeometry(
                role="corner_brace",
                source_handle="T1",
                points=((100.0, 900.0), (900.0, 100.0)),
                closed=False,
                source_layer="CORNER",
                source_entity_type="LINE",
            ),
        )
    result = DXFImportResult(
        source_path="fixture.dxf",
        source_fingerprint="A" * 64,
        layer_names=("WALER", "STRUT", "CORNER"),
        selected_layers={
            "waler": ("WALER",),
            "strut": ("STRUT",),
            "corner_brace": ("CORNER",),
        },
        layer_info=(),
        walers=walers,
        struts=struts,
        braces=(),
        corner_braces=tuple(corners),
        source_geometry=geometry,
        entity_debug=(),
        messages=(),
        source_entity_counts={},
    )
    connections, messages = build_corner_brace_connections(result)
    result = replace(result, corner_brace_connections=connections, messages=messages)
    if target_kind == "recognized":
        item = ReviewItem(
            key="recognized:corner_brace:CB71",
            display_id="CB71",
            role="corner_brace",
            status="recognized",
            member_id="CB71",
            source_handles=("T1",),
            source_layers=("CORNER",),
            source_entity_types=("INSERT",),
            selection_source="auto",
            problems=(),
            highest_severity="info",
        )
    else:
        item = ReviewItem(
            key="unresolved:corner_brace:T1",
            display_id="待修-CORNER",
            role="corner_brace",
            status="unresolved",
            member_id=None,
            source_handles=("T1",),
            source_layers=("CORNER",),
            source_entity_types=("INSERT",),
            selection_source="unresolved",
            problems=(),
            highest_severity="warning",
        )
    return result, item


def _items(result: DXFImportResult, target: ReviewItem) -> tuple[ReviewItem, ...]:
    formal = build_review_items(result, build_problem_records(result))
    if target.status == "unresolved":
        return (*formal, target)
    return formal


class CornerBraceRepairPlanningTests(unittest.TestCase):
    def test_subject_key_and_residual_hypotheses_are_deterministic_and_json_safe(self):
        result, target = _result()
        key = repair_subject_key(result, target)
        reversed_result = replace(result, source_geometry=tuple(reversed(result.source_geometry)))
        self.assertEqual(key, repair_subject_key(reversed_result, target))
        segments = target_residual_segments(result, key)
        self.assertEqual(segments, target_residual_segments(reversed_result, key))
        self.assertEqual(
            residual_axis_hypotheses(segments),
            residual_axis_hypotheses(tuple(reversed(segments))),
        )
        json.dumps(asdict(key), sort_keys=True)

    def test_subject_key_distinguishes_formal_members_with_same_source_handles(self):
        result, target = _result()
        other = _corner("CB72", (5000.0, 4000.0), (4000.0, 3000.0), "T1")
        result = replace(result, corner_braces=(*result.corner_braces, other))
        other_item = replace(
            target,
            key="recognized:corner_brace:CB72",
            display_id="CB72",
            member_id="CB72",
        )
        self.assertNotEqual(
            repair_subject_key(result, target),
            repair_subject_key(result, other_item),
        )

    def test_arbitrary_strut_material_width_does_not_change_repair_rule(self):
        candidate_lines = []
        for width in (350.0, 400.0, 500.0):
            result, target = _result(strut_width=width)
            plan = plan_corner_brace_repair(
                result,
                target,
                base_revision=0,
                review_items=_items(result, target),
            )
            self.assertTrue(plan.candidates)
            candidate_lines.append(
                (plan.candidates[0].world_start, plan.candidates[0].world_end)
            )
        self.assertEqual(candidate_lines[0], candidate_lines[1])
        self.assertEqual(candidate_lines[1], candidate_lines[2])

    def test_candidate_endpoints_come_from_finite_target_intersections(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=4,
            review_items=_items(result, target),
        )
        self.assertTrue(plan.candidates)
        candidate = plan.candidates[0]
        self.assertEqual(candidate.world_start, (0.0, 1000.0))
        self.assertEqual(candidate.world_end, (1000.0, 0.0))
        self.assertEqual(candidate.target_waler_id, "W1")
        self.assertEqual(candidate.target_strut_id, "S1")
        self.assertEqual(candidate.primary_references[0].member_id, "CB10")
        # Reference endpoints are different and must not be copied.
        self.assertNotEqual(candidate.world_start, (0.0, 4000.0))

    def test_missing_residual_or_automatic_primary_never_produces_candidate(self):
        for kwargs in ({"target_residual": False}, {"include_primary": False}):
            result, target = _result(**kwargs)
            plan = plan_corner_brace_repair(
                result,
                target,
                base_revision=0,
                review_items=_items(result, target),
            )
            self.assertEqual(plan.candidates, ())
            self.assertTrue(plan.diagnostics)

    def test_multiple_residual_guesses_without_primary_are_not_preview_candidates(self):
        result, target = _result(include_primary=False)
        result = replace(
            result,
            source_geometry=(
                *result.source_geometry,
                SourceGeometry(
                    "corner_brace",
                    "T1",
                    ((100.0, 1000.0), (1000.0, 100.0)),
                    False,
                ),
            ),
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("primary" in value for value in plan.diagnostics))

    def test_infinite_extension_without_finite_member_intersection_is_rejected(self):
        result, target = _result()
        far = SourceGeometry(
            "corner_brace", "T1", ((100.0, 8900.0), (900.0, 8100.0)), False
        )
        result = replace(result, source_geometry=(far,))
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())

    def test_invalid_reference_connection_is_not_eligible(self):
        result, target = _result()
        result = replace(
            result,
            corner_brace_connections=tuple(
                value
                for value in result.corner_brace_connections
                if value.corner_brace_id != "CB10"
            ),
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())

    def test_multiple_complete_candidates_remain_distinct_and_only_proximity_sorted(self):
        result, target = _result()
        result = replace(
            result,
            source_geometry=(
                *result.source_geometry,
                SourceGeometry(
                    "corner_brace",
                    "T1",
                    ((100.0, 1000.0), (1000.0, 100.0)),
                    False,
                ),
            ),
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertGreaterEqual(len(plan.candidates), 2)
        self.assertEqual(
            tuple(value.proximity_mm for value in plan.candidates),
            tuple(sorted(value.proximity_mm for value in plan.candidates)),
        )
        self.assertEqual(len({value.id for value in plan.candidates}), len(plan.candidates))
        self.assertTrue(all(value.primary_references for value in plan.candidates))

    def test_unresolved_creation_requires_one_unique_relationship_and_explicit_adoption(self):
        result, target = _result(target_kind="unresolved")
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertTrue(plan.candidates)
        with self.assertRaisesRegex(Exception, "explicit"):
            apply_corner_brace_repair(
                result,
                target,
                plan,
                plan.candidates[0].id,
                explicit_adoption=False,
            )
        updated, member_id = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        self.assertTrue(member_id.startswith("CB"))
        created = next(value for value in updated.corner_braces if value.id == member_id)
        self.assertIsNotNone(created.repair_provenance)
        self.assertEqual(created.selection_source, "corner_brace_repair")
        self.assertEqual(
            next(c for c in updated.corner_brace_connections if c.corner_brace_id == member_id).fixed_length_mm,
            plan.candidates[0].fixed_length_mm,
        )

    def test_unresolved_creation_rejects_multiple_surviving_relationships(self):
        result, target = _result(target_kind="unresolved")
        opposite_primary = _corner(
            "CB20",
            (5000.0, 4000.0),
            (4000.0, 3000.0),
            "P2",
        )
        result = replace(
            result,
            corner_braces=(*result.corner_braces, opposite_primary),
            source_geometry=(
                *result.source_geometry,
                SourceGeometry(
                    "corner_brace",
                    "T1",
                    ((4900.0, 900.0), (4100.0, 100.0)),
                    False,
                ),
            ),
        )
        connections, messages = build_corner_brace_connections(result)
        result = replace(
            result,
            corner_brace_connections=connections,
            messages=messages,
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())
        self.assertTrue(
            any("multiple surviving" in value for value in plan.diagnostics)
        )

    def test_unresolved_creation_rejects_duplicate_formal_geometry(self):
        result, target = _result(target_kind="unresolved")
        result = replace(
            result,
            source_geometry=(
                SourceGeometry(
                    "corner_brace",
                    "T1",
                    ((0.0, 4000.0), (1000.0, 3000.0)),
                    False,
                ),
            ),
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())
        self.assertTrue(any("Rejected hypotheses" in value for value in plan.diagnostics))

    def test_apply_rebuild_is_targeted_and_preserves_waler_contact_review(self):
        result, target = _result()
        keep_point = CandidatePoint(
            "KEEP",
            (0.0, 4000.0),
            (0.0, 4000.0),
            "manual",
            "keep",
            component_id="CB10",
        )
        result = replace(
            result,
            struts=tuple(
                replace(
                    value,
                    from_brace_to_waler_start_len=999.0,
                    from_brace_to_waler_end_len=999.0,
                    to_brace_to_waler_start_len=999.0,
                    to_brace_to_waler_end_len=999.0,
                )
                if value.id == "S1"
                else value
                for value in result.struts
            ),
            corner_braces=tuple(
                replace(
                    value,
                    candidate_points=(keep_point,),
                    selected_start_point_id="KEEP",
                    selection_source="auto",
                )
                if value.id == "CB10"
                else value
                for value in result.corner_braces
            ),
        )
        result = initialize_waler_contact_review(result)
        original_reviews = result.waler_contact_reviews
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        updated, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        untouched = next(value for value in updated.corner_braces if value.id == "CB10")
        repaired = next(value for value in updated.corner_braces if value.id == "CB71")
        repaired_strut = next(value for value in updated.struts if value.id == "S1")
        connection = next(
            value
            for value in updated.corner_brace_connections
            if value.corner_brace_id == "CB71"
        )
        self.assertEqual(untouched.candidate_points, (keep_point,))
        self.assertEqual(untouched.selected_start_point_id, "KEEP")
        self.assertEqual(updated.waler_contact_reviews, original_reviews)
        self.assertTrue(repaired.candidate_points)
        self.assertEqual(connection.strut_hole_station_mm, 1000.0)
        self.assertAlmostEqual(connection.fixed_length_mm, 2**0.5 * 1000.0)
        self.assertEqual(
            (
                repaired_strut.from_brace_to_waler_start_len,
                repaired_strut.from_brace_to_waler_end_len,
                repaired_strut.to_brace_to_waler_start_len,
                repaired_strut.to_brace_to_waler_end_len,
            ),
            (0.0, 1000, 0.0, 0.0),
        )


class CornerBraceRepairReferenceTests(unittest.TestCase):
    def test_confirmed_repaired_reference_is_secondary_never_primary(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        updated, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        items = build_review_items(updated, build_problem_records(updated))
        target_item = next(value for value in items if value.member_id == "CB71")
        confirmations = confirm_review_item(updated, target_item)
        primary, secondary = eligible_repair_references(
            updated,
            items,
            confirmations,
            excluded_member_id="CB10",
        )
        self.assertEqual(primary, ())
        self.assertEqual(len(secondary), 1)
        self.assertEqual(secondary[0].reference.reference_class, SECONDARY_REFERENCE)

    def test_repaired_only_chain_cannot_support_next_repair(self):
        result, target = _result()
        first_plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        updated, _ = apply_corner_brace_repair(
            result,
            target,
            first_plan,
            first_plan.candidates[0].id,
            explicit_adoption=True,
        )
        updated = replace(
            updated,
            corner_braces=tuple(c for c in updated.corner_braces if c.id != "CB10"),
            corner_brace_connections=tuple(
                c for c in updated.corner_brace_connections if c.corner_brace_id != "CB10"
            ),
        )
        items = build_review_items(updated, build_problem_records(updated))
        repaired_item = next(value for value in items if value.member_id == "CB71")
        confirmations = confirm_review_item(updated, repaired_item)
        new_target = replace(
            target,
            status="unresolved",
            member_id=None,
            key="unresolved:corner_brace:T1",
        )
        next_plan = plan_corner_brace_repair(
            updated,
            new_target,
            base_revision=1,
            review_items=(*items, new_target),
            confirmations=confirmations,
        )
        self.assertEqual(next_plan.candidates, ())
        self.assertTrue(any("primary" in value for value in next_plan.diagnostics))

    def test_unconfirmed_or_requires_review_repaired_member_is_not_secondary(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        updated, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        items = build_review_items(updated, build_problem_records(updated))
        primary, secondary = eligible_repair_references(updated, items, {})
        self.assertTrue(primary)
        self.assertEqual(secondary, ())
        repaired = next(value for value in updated.corner_braces if value.id == "CB71")
        assert repaired.repair_provenance is not None
        repaired_item = next(value for value in items if value.member_id == "CB71")
        confirmations = confirm_review_item(updated, repaired_item)
        _, secondary = eligible_repair_references(
            updated,
            items,
            confirmations,
            requires_review_subjects=(
                __import__("dxf_import.corner_brace_repair", fromlist=["_subject_token"])._subject_token(
                    repaired.repair_provenance.subject_key
                ),
            ),
        )
        self.assertEqual(secondary, ())

    def test_repaired_member_with_excluded_source_or_invalid_connection_is_not_secondary(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired_result, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        items = build_review_items(
            repaired_result,
            build_problem_records(repaired_result),
        )
        repaired_item = next(value for value in items if value.member_id == "CB71")
        confirmations = confirm_review_item(repaired_result, repaired_item)

        invalid_connection = replace(
            repaired_result,
            corner_brace_connections=tuple(
                value
                for value in repaired_result.corner_brace_connections
                if value.corner_brace_id != "CB71"
            ),
        )
        _, secondary = eligible_repair_references(
            invalid_connection,
            items,
            confirmations,
            excluded_member_id="CB10",
        )
        self.assertEqual(secondary, ())

        excluded_source = replace(
            repaired_result,
            excluded_sources=(
                ExcludedSource("corner_brace", ("T1",)),
            ),
        )
        _, secondary = eligible_repair_references(
            excluded_source,
            items,
            confirmations,
            excluded_member_id="CB10",
        )
        self.assertEqual(secondary, ())


class CornerBraceRepairWorkflowTests(unittest.TestCase):
    class _Importer:
        tolerances = GeometryTolerances()
        source_fingerprint = "A" * 64
        layer_names = ("WALER", "STRUT", "CORNER")

    def _workflow(self) -> tuple[DXFReviewWorkflow, ReviewItem]:
        result, _target = _result()
        workflow = DXFReviewWorkflow(
            self._Importer(),
            "fixture.dxf",
            initial_world_result=result,
        )
        target = next(item for item in workflow.review_items if item.member_id == "CB71")
        return workflow, target

    def test_commit_is_atomic_and_updates_target_derived_state(self):
        workflow, target = self._workflow()
        assert workflow.result is not None
        strut_item = next(item for item in workflow.review_items if item.member_id == "S1")
        workflow.review_confirmations = confirm_review_item(
            workflow.result,
            target,
            workflow.review_confirmations,
        )
        workflow.review_confirmations = confirm_review_item(
            workflow.result,
            strut_item,
            workflow.review_confirmations,
        )
        plan = workflow.plan_corner_brace_repair(target.key)
        mutation = workflow.commit_corner_brace_repair(plan, plan.candidates[0].id)
        self.assertTrue(mutation.changed)
        self.assertCountEqual(mutation.invalidated_confirmations, ("CB71", "S1"))
        assert workflow.world_result is not None
        repaired = next(value for value in workflow.world_result.corner_braces if value.id == "CB71")
        self.assertEqual(repaired.start, (0.0, 1000.0))
        self.assertTrue(
            any(
                value > 0
                for value in (
                    workflow.world_result.struts[0].from_brace_to_waler_start_len,
                    workflow.world_result.struts[0].from_brace_to_waler_end_len,
                )
            )
        )
        self.assertEqual(workflow.revision, plan.base_revision + 1)

    def test_stale_plan_is_rejected_without_mutation(self):
        workflow, target = self._workflow()
        plan = workflow.plan_corner_brace_repair(target)
        primary = next(item for item in workflow.review_items if item.member_id == "CB10")
        self.assertTrue(workflow.confirm(primary))
        before = workflow.snapshot
        with self.assertRaisesRegex(Exception, "changed"):
            workflow.commit_corner_brace_repair(plan, plan.candidates[0].id)
        self.assertIs(workflow.world_result, before.world_result)
        self.assertEqual(workflow.revision, before.revision)

    def test_staged_failure_leaves_every_live_projection_unchanged(self):
        workflow, target = self._workflow()
        plan = workflow.plan_corner_brace_repair(target)
        before = workflow.snapshot
        before_store = workflow.candidate_point_store
        with patch(
            "dxf_import.review_workflow.build_review_items",
            side_effect=RuntimeError("projection failed"),
        ):
            with self.assertRaisesRegex(RuntimeError, "projection failed"):
                workflow.commit_corner_brace_repair(plan, plan.candidates[0].id)
        self.assertIs(workflow.world_result, before.world_result)
        self.assertIs(workflow.result, before.result)
        self.assertEqual(workflow.problem_records, before.problem_records)
        self.assertEqual(workflow.review_items, before.review_items)
        self.assertEqual(workflow.review_confirmations, before.review_confirmations)
        self.assertIs(workflow.candidate_point_store, before_store)
        self.assertEqual(workflow.revision, before.revision)


class CornerBraceRepairPersistenceTests(unittest.TestCase):
    def test_optional_manual_override_payload_round_trips_without_version_change(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        override = next(
            value
            for value in capture_manual_overrides(repaired)
            if value.corner_brace_repair is not None
        )
        parsed = manual_override_from_mapping(asdict(override))
        self.assertEqual(parsed, override)
        legacy = manual_override_from_mapping(
            {"role": "corner_brace", "source_handles": ["T1"]}
        )
        self.assertIsNotNone(legacy)
        assert legacy is not None
        self.assertIsNone(legacy.corner_brace_repair)

    def test_same_fingerprint_replay_revalidates_and_restores_repair(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        overrides = capture_manual_overrides(repaired)
        replayed, report = replay_manual_overrides(result, overrides)
        replayed_target = next(value for value in replayed.corner_braces if value.id == "CB71")
        self.assertEqual(replayed_target.start, (0.0, 1000.0))
        self.assertIsNotNone(replayed_target.repair_provenance)
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.preserved))

    def test_same_fingerprint_replay_does_not_substitute_changed_primary(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        overrides = capture_manual_overrides(repaired)
        changed_primary = _corner("CB11", (0.0, 4000.0), (1000.0, 3000.0), "P2")
        changed = replace(
            result,
            corner_braces=tuple(
                changed_primary if value.id == "CB10" else value
                for value in result.corner_braces
            ),
        )
        connections, messages = build_corner_brace_connections(changed)
        changed = replace(changed, corner_brace_connections=connections, messages=messages)
        replayed, report = replay_manual_overrides(changed, overrides)
        replayed_target = next(value for value in replayed.corner_braces if value.id == "CB71")
        self.assertIsNone(replayed_target.repair_provenance)
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.needs_review))

    def test_replay_fails_when_primary_is_missing_even_if_saved_secondary_exists(self):
        result, target = _result()
        primary_item = next(
            value
            for value in _items(result, target)
            if value.member_id == "CB10"
        )
        secondary_provenance = CornerBraceRepairProvenance(
            subject_key=CornerBraceRepairSubjectKey(
                source_fingerprint=result.source_fingerprint,
                source_handles=("R1",),
                target_kind="recognized",
                base_geometry_key="R1-AXIS",
            ),
            adopted_world_start=(0.0, 3000.0),
            adopted_world_end=(1000.0, 2000.0),
            target_waler_identity="waler:R1",
            target_strut_identity="strut:R1",
            automatic_primary_references=(
                CornerBraceRepairReference(
                    repair_subject_key(result, primary_item),
                    "CB10",
                    PRIMARY_REFERENCE,
                ),
            ),
            preferred_display_id="CB20",
            evidence_signature="SECONDARY",
        )
        secondary = _corner(
            "CB20",
            (0.0, 3000.0),
            (1000.0, 2000.0),
            "R1",
            selection_source="corner_brace_repair",
            provenance=secondary_provenance,
        )
        result = replace(
            result,
            struts=(*result.struts, _strut("S3", 2000.0)),
            corner_braces=(*result.corner_braces, secondary),
        )
        connections, messages = build_corner_brace_connections(result)
        result = replace(
            result,
            corner_brace_connections=connections,
            messages=messages,
        )
        items = build_review_items(result, build_problem_records(result))
        secondary_item = next(value for value in items if value.member_id == "CB20")
        confirmations = confirm_review_item(result, secondary_item)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=items,
            confirmations=confirmations,
        )
        self.assertTrue(plan.candidates[0].secondary_references)
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        target_override = next(
            value
            for value in capture_manual_overrides(repaired)
            if value.display_id == "CB71"
        )

        replay_base = replace(
            result,
            corner_braces=tuple(
                value for value in result.corner_braces if value.id != "CB10"
            ),
        )
        connections, messages = build_corner_brace_connections(replay_base)
        replay_base = replace(
            replay_base,
            corner_brace_connections=connections,
            messages=messages,
        )
        replay_items = build_review_items(
            replay_base,
            build_problem_records(replay_base),
        )
        replay_secondary_item = next(
            value for value in replay_items if value.member_id == "CB20"
        )
        replay_confirmations = confirm_review_item(
            replay_base,
            replay_secondary_item,
        )
        replayed, report = replay_manual_overrides(
            replay_base,
            (target_override,),
            review_confirmations=replay_confirmations,
        )
        replayed_target = next(
            value for value in replayed.corner_braces if value.id == "CB71"
        )
        self.assertIsNone(replayed_target.repair_provenance)
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.needs_review))

    def test_same_fingerprint_replay_does_not_interchange_same_handle_members(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        overrides = capture_manual_overrides(repaired)
        other = _corner("CB72", (5000.0, 4000.0), (4000.0, 3000.0), "T1")
        replay_base = replace(result, corner_braces=(*result.corner_braces, other))
        connections, messages = build_corner_brace_connections(replay_base)
        replay_base = replace(
            replay_base,
            corner_brace_connections=connections,
            messages=messages,
        )
        replayed, report = replay_manual_overrides(replay_base, overrides)
        replayed_target = next(value for value in replayed.corner_braces if value.id == "CB71")
        untouched = next(value for value in replayed.corner_braces if value.id == "CB72")
        self.assertIsNotNone(replayed_target.repair_provenance)
        self.assertIsNone(untouched.repair_provenance)
        self.assertEqual(untouched.start, other.start)
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.preserved))

    def test_unresolved_replay_reports_preferred_id_conflict_without_creating_member(self):
        result, _ = _result(target_kind="unresolved")
        unresolved_message = ValidationMessage(
            "warning",
            "CORNER_BRACE_UNRESOLVED",
            "CornerBrace source requires review.",
            role="corner_brace",
            source_handles=("T1",),
        )
        result = replace(result, messages=(unresolved_message,))
        target = next(
            item
            for item in build_review_items(result, build_problem_records(result))
            if item.status == "unresolved" and item.source_handles == ("T1",)
        )
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, created_id = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        self.assertEqual(created_id, "CB11")
        overrides = capture_manual_overrides(repaired)

        conflict = _corner("CB11", (5000.0, 4000.0), (4000.0, 3000.0), "Q1")
        replay_base = replace(result, corner_braces=(*result.corner_braces, conflict))
        connections, messages = build_corner_brace_connections(replay_base)
        replay_base = replace(
            replay_base,
            corner_brace_connections=connections,
            messages=(*messages, unresolved_message),
        )
        replayed, report = replay_manual_overrides(replay_base, overrides)
        self.assertEqual(
            [value.id for value in replayed.corner_braces].count("CB11"),
            1,
        )
        self.assertIsNone(
            next(value for value in replayed.corner_braces if value.id == "CB11").repair_provenance
        )
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.needs_review))

    def test_changed_content_recovery_never_geometry_rebinds_repair(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        repaired, _ = apply_corner_brace_repair(
            result,
            target,
            plan,
            plan.candidates[0].id,
            explicit_adoption=True,
        )
        repair_override = next(
            value
            for value in capture_manual_overrides(repaired)
            if value.corner_brace_repair is not None
        )
        exact_entries = ReviewRecoveryPlanner._repair_recovery_entries(
            (repair_override,),
            result,
        )
        self.assertEqual(exact_entries[0].category, RecoveryCategory.REQUIRES_REVIEW)
        changed_identity = replace(
            result,
            corner_braces=tuple(value for value in result.corner_braces if value.id != "CB71"),
            source_geometry=(
                SourceGeometry(
                    "corner_brace",
                    "OTHER",
                    ((100.0, 900.0), (900.0, 100.0)),
                    False,
                ),
            ),
        )
        disabled_entries = ReviewRecoveryPlanner._repair_recovery_entries(
            (repair_override,),
            changed_identity,
        )
        self.assertEqual(disabled_entries[0].category, RecoveryCategory.DISABLED)
        summary = RecoverySummary((*exact_entries, *disabled_entries))
        self.assertEqual(summary.counts[RecoveryCategory.REQUIRES_REVIEW], 1)
        self.assertEqual(summary.counts[RecoveryCategory.DISABLED], 1)

if __name__ == "__main__":
    unittest.main()
