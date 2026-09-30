from __future__ import annotations

from dataclasses import asdict, replace
import json
import unittest
from unittest.mock import patch

from dxf_import.corner_brace_repair import (
    CornerBraceLocalTemplate,
    PRIMARY_REFERENCE,
    SECONDARY_REFERENCE,
    TargetRelationshipFrame,
    apply_corner_brace_repair,
    eligible_repair_references,
    extract_corner_brace_local_template,
    extract_target_repair_evidence,
    plan_corner_brace_repair,
    repair_subject_key,
    residual_axis_hypotheses,
    target_residual_segments,
    transfer_corner_brace_template,
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


def _fb7_cb58_result() -> tuple[DXFImportResult, ReviewItem]:
    """Portable WCS characterization of the Y05 FB7 / CB58 relationship."""

    offset = 1712.030
    walers = (
        replace(
            _waler("W2", 0.0),
            start=(0.0, -5000.0),
            end=(0.0, 5000.0),
            world_start=(0.0, -5000.0),
            world_end=(0.0, 5000.0),
        ),
        replace(
            _waler("W1", 5000.0),
            start=(5000.0, -5000.0),
            end=(5000.0, 5000.0),
            world_start=(5000.0, -5000.0),
            world_end=(5000.0, 5000.0),
        ),
    )
    s21 = replace(
        _strut("S21", 0.0),
        from_waler="W2",
        to_waler="W1",
    )
    s22 = replace(
        _strut("S22", 3200.0),
        from_waler="W2",
        to_waler="W1",
    )
    corners = (
        _corner("FB7", (0.0, -1640.632), (1640.632, 0.0), "FB7"),
        _corner("CB58", (0.0, offset), (offset, 0.0), "CB58"),
        _corner("CB64", (0.0, 4800.0), (1600.0, 3200.0), "CB64"),
        _corner("CB20", (5000.0, 4800.0), (3400.0, 3200.0), "CB20"),
    )
    geometry = (
        SourceGeometry(
            "corner_brace",
            "FB7",
            ((300.0, -1412.03), (900.0, -812.03)),
            False,
            source_layer="S-BEAM",
            source_entity_type="LINE",
        ),
        SourceGeometry(
            "corner_brace",
            "FB7",
            ((-75.0, -1787.03), (75.0, -1787.03), (75.0, -1637.03), (-75.0, -1637.03)),
            True,
            source_layer="S-BEAM",
            source_entity_type="LWPOLYLINE",
        ),
    )
    result = DXFImportResult(
        source_path="y05-fb7-minimal.dxf",
        source_fingerprint="F" * 64,
        layer_names=("WALER", "STRUT", "S-BEAM"),
        selected_layers={
            "waler": ("WALER",),
            "strut": ("STRUT",),
            "corner_brace": ("S-BEAM",),
        },
        layer_info=(),
        walers=walers,
        struts=(s21, s22),
        braces=(),
        corner_braces=corners,
        source_geometry=geometry,
        entity_debug=(),
        messages=(),
        source_entity_counts={},
    )
    connections, messages = build_corner_brace_connections(result)
    result = replace(result, corner_brace_connections=connections, messages=messages)
    target = ReviewItem(
        key="recognized:corner_brace:FB7",
        display_id="FB7",
        role="corner_brace",
        status="recognized",
        member_id="FB7",
        source_handles=("FB7",),
        source_layers=("S-BEAM",),
        source_entity_types=("INSERT",),
        selection_source="auto",
        problems=(),
        highest_severity="warning",
    )
    return result, target


class CornerBraceRepairPlanningTests(unittest.TestCase):
    def test_fb7_cb58_fixture_preserves_measured_local_template(self):
        result, target = _fb7_cb58_result()
        primary, _secondary = eligible_repair_references(
            result,
            _items(result, target),
            {},
            excluded_member_id="FB7",
        )
        cb58 = next(value for value in primary if value.reference.member_id == "CB58")
        template = extract_corner_brace_local_template(result, cb58)
        self.assertIsNotNone(template)
        assert template is not None
        self.assertAlmostEqual(template.waler_offset_mm, 1712.030, places=3)
        self.assertAlmostEqual(template.strut_station_mm, 1712.030, places=3)
        self.assertAlmostEqual(template.fixed_length_mm, 2421.177, places=2)
        # The fixed length is retained only for audit/diagnostic display.
        self.assertEqual(template.reference.member_id, "CB58")

    def test_fb7_uses_cb58_mirrored_target_frame_transfer(self):
        result, target = _fb7_cb58_result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertTrue(plan.candidates)
        candidate = plan.candidates[0]
        self.assertEqual(candidate.target_waler_id, "W2")
        self.assertEqual(candidate.target_strut_id, "S21")
        self.assertEqual(candidate.template_reference.member_id, "CB58")
        self.assertEqual(candidate.transfer_mode, "mirrored")
        self.assertAlmostEqual(candidate.world_start[0], 0.0, places=6)
        self.assertAlmostEqual(candidate.world_start[1], -1712.030, places=3)
        self.assertAlmostEqual(candidate.world_end[0], 1712.030, places=3)
        self.assertAlmostEqual(candidate.world_end[1], 0.0, places=6)
        self.assertNotAlmostEqual(candidate.fixed_length_mm, 2320.204, places=3)
        self.assertTrue(
            any("僅供稽核與診斷" in value for value in candidate.diagnostics)
        )

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

    def test_target_evidence_is_exact_source_deterministic_and_closed_edges_are_not_axes(self):
        result, target = _fb7_cb58_result()
        key = repair_subject_key(result, target)
        evidence = extract_target_repair_evidence(result, key)
        reversed_result = replace(result, source_geometry=tuple(reversed(result.source_geometry)))
        self.assertEqual(evidence, extract_target_repair_evidence(reversed_result, key))
        self.assertEqual(len(evidence.direction_hypotheses), 1)
        self.assertEqual(
            {anchor.kind for anchor in evidence.positional_anchors},
            {"plate", "corridor"},
        )
        self.assertTrue(
            all(
                abs(abs((line[1][1] - line[0][1]) / (line[1][0] - line[0][0])) - 1.0)
                < 1e-9
                for line in evidence.direction_hypotheses
            )
        )

    def test_target_direction_and_anchor_are_both_hard_gates(self):
        result, target = _fb7_cb58_result()
        closed_only = replace(result, source_geometry=(result.source_geometry[1],))
        far_corridor = replace(
            result,
            source_geometry=(
                SourceGeometry(
                    "corner_brace",
                    "FB7",
                    ((10000.0, 10000.0), (10600.0, 10600.0)),
                    False,
                ),
            ),
        )
        for value in (closed_only, far_corridor):
            with self.subTest(source_geometry=value.source_geometry):
                plan = plan_corner_brace_repair(
                    value,
                    target,
                    base_revision=0,
                    review_items=_items(value, target),
                )
                self.assertEqual(plan.candidates, ())

    def test_template_extraction_is_endpoint_order_independent_and_length_is_audit_only(self):
        result, target = _fb7_cb58_result()
        primary, _ = eligible_repair_references(
            result,
            _items(result, target),
            {},
            excluded_member_id="FB7",
        )
        original = next(value for value in primary if value.reference.member_id == "CB58")
        template = extract_corner_brace_local_template(result, original)
        assert template is not None
        reversed_corner = replace(
            next(value for value in result.corner_braces if value.id == "CB58"),
            start=(1712.03, 0.0),
            end=(0.0, 1712.03),
            world_start=(1712.03, 0.0),
            world_end=(0.0, 1712.03),
        )
        reversed_result = replace(
            result,
            corner_braces=tuple(
                reversed_corner if value.id == "CB58" else value
                for value in result.corner_braces
            ),
        )
        connections, messages = build_corner_brace_connections(reversed_result)
        reversed_result = replace(
            reversed_result,
            corner_brace_connections=connections,
            messages=messages,
        )
        reversed_primary, _ = eligible_repair_references(
            reversed_result,
            _items(reversed_result, target),
            {},
            excluded_member_id="FB7",
        )
        reversed_template = extract_corner_brace_local_template(
            reversed_result,
            next(value for value in reversed_primary if value.reference.member_id == "CB58"),
        )
        assert reversed_template is not None
        self.assertEqual(template.waler_offset_mm, reversed_template.waler_offset_mm)
        self.assertEqual(template.strut_station_mm, reversed_template.strut_station_mm)

        changed_connection = replace(original.connection, fixed_length_mm=9999.0)
        changed_template = extract_corner_brace_local_template(
            result,
            replace(original, connection=changed_connection),
        )
        assert changed_template is not None
        self.assertEqual(template.waler_offset_mm, changed_template.waler_offset_mm)
        self.assertEqual(template.strut_station_mm, changed_template.strut_station_mm)
        self.assertEqual(changed_template.fixed_length_mm, 9999.0)

    def test_template_extraction_rejects_nonfinite_off_segment_and_degenerate_frames(self):
        result, target = _fb7_cb58_result()
        primary, _ = eligible_repair_references(
            result,
            _items(result, target),
            {},
            excluded_member_id="FB7",
        )
        evidence = next(value for value in primary if value.reference.member_id == "CB58")
        self.assertIsNone(
            extract_corner_brace_local_template(
                result,
                replace(
                    evidence,
                    connection=replace(
                        evidence.connection,
                        baseline_waler_attachment=(float("nan"), 0.0),
                    ),
                ),
            )
        )
        self.assertIsNone(
            extract_corner_brace_local_template(
                result,
                replace(
                    evidence,
                    connection=replace(
                        evidence.connection,
                        baseline_waler_attachment=(0.0, 99999.0),
                    ),
                ),
            )
        )
        parallel = replace(
            result,
            walers=tuple(
                replace(
                    value,
                    start=(0.0, 0.0),
                    end=(5000.0, 0.0),
                    world_start=(0.0, 0.0),
                    world_end=(5000.0, 0.0),
                )
                if value.id == "W2"
                else value
                for value in result.walers
            ),
        )
        self.assertIsNone(extract_corner_brace_local_template(parallel, evidence))

    def test_template_transfer_uses_only_target_frame_local_values(self):
        reference = CornerBraceRepairReference(
            CornerBraceRepairSubjectKey("A" * 64, ("R",), "recognized", "R"),
            "CB-R",
            PRIMARY_REFERENCE,
        )
        template = CornerBraceLocalTemplate(
            reference=reference,
            topology="from",
            side=1,
            waler_offset_mm=1200.0,
            strut_station_mm=800.0,
            fixed_length_mm=9999.0,
            relationship_waler_id="WR",
            relationship_strut_id="SR",
        )
        frame = TargetRelationshipFrame(
            waler_id="WT",
            strut_id="ST",
            endpoint_name="from",
            origin=(1000.0, 2000.0),
            inward=(0.0, 1.0),
            waler_axis=(1.0, 0.0),
            waler_line=((-1000.0, 2000.0), (3000.0, 2000.0)),
            strut_line=((1000.0, 2000.0), (1000.0, 5000.0)),
        )
        same_side = transfer_corner_brace_template(frame, template, "same_side")
        mirrored = transfer_corner_brace_template(frame, template, "mirrored")
        self.assertEqual(same_side, ((-200.0, 2000.0), (1000.0, 2800.0)))
        self.assertEqual(mirrored, ((2200.0, 2000.0), (1000.0, 2800.0)))
        self.assertNotAlmostEqual(
            ((same_side[0][0] - same_side[1][0]) ** 2 + (same_side[0][1] - same_side[1][1]) ** 2) ** 0.5,
            template.fixed_length_mm,
        )

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

        missing_residual, target = _result(target_residual=False)
        residual_plan = plan_corner_brace_repair(
            missing_residual,
            target,
            base_revision=0,
            review_items=_items(missing_residual, target),
        )
        self.assertIn("目標來源沒有可靠的方向證據。", residual_plan.diagnostics)
        self.assertIn("目標來源沒有定位錨點證據。", residual_plan.diagnostics)

        missing_primary, target = _result(include_primary=False)
        primary_plan = plan_corner_brace_repair(
            missing_primary,
            target,
            base_revision=0,
            review_items=_items(missing_primary, target),
        )
        self.assertIn(
            "沒有符合條件的自動辨識角撐可作為主要參考。",
            primary_plan.diagnostics,
        )

        result, target = _result()
        with patch(
            "dxf_import.corner_brace_repair.extract_corner_brace_local_template",
            return_value=None,
        ):
            invalid_template_plan = plan_corner_brace_repair(
                result,
                target,
                base_revision=0,
                review_items=_items(result, target),
            )
        self.assertIn(
            "沒有任何自動主要參考可建立有效的有限局部模板。",
            invalid_template_plan.diagnostics,
        )

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
        self.assertTrue(any("主要參考" in value for value in plan.diagnostics))

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

    def test_incompatible_endpoint_topology_cannot_become_a_template(self):
        result, target = _result(include_primary=False)
        to_side = _corner("CB20", (5000.0, 4000.0), (4000.0, 3000.0), "P2")
        result = replace(result, corner_braces=(*result.corner_braces, to_side))
        connections, messages = build_corner_brace_connections(result)
        result = replace(result, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(plan.candidates, ())

    def test_local_angle_incompatibility_and_out_of_range_transfer_are_rejected(self):
        result, target = _result(include_primary=False)
        diagonal = Strut(
            "S3",
            (0.0, 3000.0),
            (3000.0, 6000.0),
            "STRUT",
            ("S-S3",),
            ("LINE",),
            "existing_centerline",
            False,
            400.0,
            "W1",
            "W2",
            1.0,
        )
        diagonal_reference = _corner(
            "CB30",
            (0.0, 4000.0),
            (700.0, 3700.0),
            "P3",
        )
        incompatible = replace(
            result,
            struts=(*result.struts, diagonal),
            corner_braces=(*result.corner_braces, diagonal_reference),
        )
        connections, messages = build_corner_brace_connections(incompatible)
        incompatible = replace(
            incompatible,
            corner_brace_connections=connections,
            messages=messages,
        )
        plan = plan_corner_brace_repair(
            incompatible,
            target,
            base_revision=0,
            review_items=_items(incompatible, target),
        )
        self.assertEqual(plan.candidates, ())

        long_w2 = replace(
            next(value for value in result.walers if value.id == "W2"),
            start=(5000.0, -10000.0),
            end=(5000.0, 10000.0),
            world_start=(5000.0, -10000.0),
            world_end=(5000.0, 10000.0),
        )
        far_reference = _corner(
            "CB40",
            (5000.0, 6000.0),
            (2000.0, 3000.0),
            "P4",
        )
        outside = replace(
            result,
            walers=tuple(long_w2 if value.id == "W2" else value for value in result.walers),
            corner_braces=(*result.corner_braces, far_reference),
            source_geometry=(
                SourceGeometry(
                    "corner_brace",
                    "T1",
                    ((100.0, -2900.0), (900.0, -2100.0)),
                    False,
                ),
            ),
        )
        connections, messages = build_corner_brace_connections(outside)
        outside = replace(outside, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            outside,
            target,
            base_revision=0,
            review_items=_items(outside, target),
        )
        self.assertEqual(plan.candidates, ())

    def test_nearest_invalid_reference_is_skipped_for_next_compatible_primary(self):
        result, target = _fb7_cb58_result()
        invalid = _corner("CB00", (0.0, -1500.0), (200.0, -1300.0), "BAD")
        result = replace(result, corner_braces=(invalid, *result.corner_braces))
        # Keep CB00 deliberately outside the current connection truth.
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertTrue(plan.candidates)
        self.assertEqual(plan.candidates[0].template_reference.member_id, "CB58")

    def test_reference_entity_order_does_not_change_ranking(self):
        result, target = _fb7_cb58_result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        reordered = replace(
            result,
            corner_braces=tuple(reversed(result.corner_braces)),
            corner_brace_connections=tuple(reversed(result.corner_brace_connections)),
        )
        reordered_plan = plan_corner_brace_repair(
            reordered,
            target,
            base_revision=0,
            review_items=_items(reordered, target),
        )
        self.assertEqual(plan.candidates, reordered_plan.candidates)

    def test_same_tier_near_non_equivalent_templates_remain_preview_candidates(self):
        result, target = _fb7_cb58_result()
        result = replace(result, source_geometry=(result.source_geometry[0],))
        cb59 = _corner("CB59", (0.0, 1680.0), (1680.0, 0.0), "CB59")
        result = replace(result, corner_braces=(*result.corner_braces, cb59))
        connections, messages = build_corner_brace_connections(result)
        result = replace(result, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
            tolerances=GeometryTolerances(ambiguous_connection_delta_mm=50.0),
        )
        self.assertEqual(
            {candidate.template_reference.member_id for candidate in plan.candidates},
            {"CB58", "CB59"},
        )
        self.assertEqual(len({candidate.fixed_length_mm for candidate in plan.candidates}), 2)

    def test_recognized_target_may_preview_multiple_unique_relationships(self):
        result, target = _result()
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
        result = replace(result, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertEqual(
            {(value.target_waler_id, value.target_strut_id) for value in plan.candidates},
            {("W1", "S1"), ("W2", "S1")},
        )
        self.assertTrue(all(value.template_reference for value in plan.candidates))

    def test_unresolved_single_relationship_keeps_multiple_template_candidates(self):
        result, target = _fb7_cb58_result()
        result = replace(
            result,
            source_geometry=(result.source_geometry[0],),
            corner_braces=tuple(
                value for value in result.corner_braces if value.id != "FB7"
            ),
        )
        target = replace(
            target,
            key="unresolved:corner_brace:FB7",
            status="unresolved",
            member_id=None,
            selection_source="unresolved",
        )
        cb59 = _corner("CB59", (0.0, 1680.0), (1680.0, 0.0), "CB59")
        result = replace(result, corner_braces=(*result.corner_braces, cb59))
        connections, messages = build_corner_brace_connections(result)
        result = replace(result, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
            tolerances=GeometryTolerances(ambiguous_connection_delta_mm=50.0),
        )
        self.assertEqual(len(plan.candidates), 2)
        self.assertEqual(
            {(value.target_waler_id, value.target_strut_id) for value in plan.candidates},
            {("W2", "S21")},
        )

    def test_selected_template_is_not_derived_from_supporting_tuple_order(self):
        result, target = _fb7_cb58_result()
        duplicate = _corner("CB59", (0.0, 1712.03), (1712.03, 0.0), "CB59")
        result = replace(result, corner_braces=(*result.corner_braces, duplicate))
        connections, messages = build_corner_brace_connections(result)
        result = replace(result, corner_brace_connections=connections, messages=messages)
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        candidate = plan.candidates[0]
        self.assertGreaterEqual(len(candidate.primary_references), 2)
        reordered = replace(
            candidate,
            primary_references=tuple(reversed(candidate.primary_references)),
        )
        self.assertEqual(reordered.template_reference, candidate.template_reference)
        self.assertEqual(reordered.id, candidate.id)

    def test_equivalent_complete_candidates_are_deterministically_deduplicated(self):
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
        self.assertEqual(len(plan.candidates), 1)
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
        with self.assertRaisesRegex(Exception, "明確採用"):
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

    def test_apply_failure_reasons_are_chinese(self):
        result, target = _result()
        plan = plan_corner_brace_repair(
            result,
            target,
            base_revision=0,
            review_items=_items(result, target),
        )
        self.assertTrue(plan.candidates)

        with self.assertRaisesRegex(Exception, "所選角撐修補候選不符合資格"):
            apply_corner_brace_repair(
                result,
                target,
                plan,
                "missing-candidate",
                explicit_adoption=True,
            )

        with self.assertRaisesRegex(Exception, "圍令／支撐關係已不存在"):
            apply_corner_brace_repair(
                replace(result, walers=()),
                target,
                plan,
                plan.candidates[0].id,
                explicit_adoption=True,
            )

        without_target = replace(
            result,
            corner_braces=tuple(
                value for value in result.corner_braces if value.id != "CB71"
            ),
        )
        with self.assertRaisesRegex(Exception, "已辨識的角撐修補目標已不存在"):
            apply_corner_brace_repair(
                without_target,
                target,
                plan,
                plan.candidates[0].id,
                explicit_adoption=True,
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
            any("多組仍有效" in value for value in plan.diagnostics)
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
        self.assertTrue(any("已拒絕假設" in value for value in plan.diagnostics))

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
        self.assertTrue(any("主要參考" in value for value in next_plan.diagnostics))

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
        with self.assertRaisesRegex(Exception, "已變更"):
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

    def test_template_mode_or_local_value_tampering_is_stale_and_atomic(self):
        workflow, target = self._workflow()
        plan = workflow.plan_corner_brace_repair(target)
        original = plan.candidates[0]
        for changed in (
            replace(original, transfer_mode="mirrored"),
            replace(
                original,
                reference_waler_offset_mm=original.reference_waler_offset_mm + 1.0,
            ),
            replace(
                original,
                reference_strut_station_mm=original.reference_strut_station_mm + 1.0,
            ),
        ):
            with self.subTest(changed=changed):
                tampered = replace(plan, candidates=(changed,))
                before = workflow.snapshot
                before_store = workflow.candidate_point_store
                with self.assertRaisesRegex(Exception, "已過期"):
                    workflow.commit_corner_brace_repair(tampered, changed.id)
                self.assertIs(workflow.world_result, before.world_result)
                self.assertIs(workflow.result, before.result)
                self.assertEqual(workflow.review_items, before.review_items)
                self.assertEqual(
                    workflow.review_confirmations,
                    before.review_confirmations,
                )
                self.assertIs(workflow.candidate_point_store, before_store)
                self.assertEqual(workflow.revision, before.revision)

    def test_selected_template_connection_change_is_stale_without_commit_mutation(self):
        workflow, target = self._workflow()
        plan = workflow.plan_corner_brace_repair(target)
        assert workflow.world_result is not None
        before_connection_change = workflow.snapshot
        changed_connections = tuple(
            replace(
                value,
                baseline_waler_attachment=(
                    value.baseline_waler_attachment[0],
                    value.baseline_waler_attachment[1] + 60.0,
                ),
            )
            if value.corner_brace_id == plan.candidates[0].template_reference.member_id
            else value
            for value in workflow.world_result.corner_brace_connections
        )
        workflow.world_result = replace(
            workflow.world_result,
            corner_brace_connections=changed_connections,
        )
        baseline = workflow.snapshot
        before_store = workflow.candidate_point_store
        with self.assertRaisesRegex(Exception, "已過期|符合資格"):
            workflow.commit_corner_brace_repair(plan, plan.candidates[0].id)
        self.assertIs(workflow.world_result, baseline.world_result)
        self.assertIs(workflow.result, baseline.result)
        self.assertEqual(workflow.review_items, baseline.review_items)
        self.assertEqual(workflow.review_confirmations, baseline.review_confirmations)
        self.assertIs(workflow.candidate_point_store, before_store)
        self.assertEqual(workflow.revision, baseline.revision)
        self.assertIsNot(workflow.world_result, before_connection_change.world_result)


class CornerBraceRepairPersistenceTests(unittest.TestCase):
    def test_relationship_selection_provenance_round_trips_without_template(self):
        result, target = _result()
        subject_key = repair_subject_key(result, target)
        provenance = CornerBraceRepairProvenance(
            subject_key=subject_key,
            adopted_world_start=(0.0, 150.0),
            adopted_world_end=(1000.0, 150.0),
            target_waler_identity="waler:W-W1",
            target_strut_identity="strut:S-S1",
            automatic_primary_references=(),
            selected_template_reference=None,
            transfer_mode="body_relationship_selection",
            reference_waler_offset_mm=0.0,
            reference_strut_station_mm=0.0,
            preferred_display_id="CB99",
            selection_mode="body_relationship_selection",
            body_signature="BODY-SIGNATURE",
        )
        repaired = replace(
            _corner("CB99", (0.0, 150.0), (1000.0, 150.0), "T1"),
            selection_source="corner_brace_repair",
            repair_provenance=provenance,
        )
        staged = replace(result, corner_braces=(*result.corner_braces, repaired))
        override = next(
            value
            for value in capture_manual_overrides(staged)
            if value.corner_brace_repair == provenance
        )

        parsed = manual_override_from_mapping(asdict(override))

        self.assertEqual(parsed, override)

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

        payload = asdict(override)
        repair_payload = payload["corner_brace_repair"]
        repair_payload.pop("reference_strut_station_mm")
        partial = manual_override_from_mapping(payload)
        self.assertIsNotNone(partial)
        assert partial is not None
        self.assertIsNone(partial.corner_brace_repair)

    def test_legacy_payload_replays_adopted_line_without_new_ranking(self):
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
        payload = asdict(override)
        legacy_payload = payload["corner_brace_repair"]
        for key in (
            "selected_template_reference",
            "transfer_mode",
            "reference_waler_offset_mm",
            "reference_strut_station_mm",
        ):
            legacy_payload.pop(key)
        legacy_override = manual_override_from_mapping(payload)
        self.assertIsNotNone(legacy_override)
        assert legacy_override is not None
        self.assertIsNotNone(legacy_override.corner_brace_repair)
        assert legacy_override.corner_brace_repair is not None
        self.assertIsNone(
            legacy_override.corner_brace_repair.selected_template_reference
        )
        reserialized_legacy = manual_override_from_mapping(asdict(legacy_override))
        self.assertIsNotNone(reserialized_legacy)
        assert reserialized_legacy is not None
        self.assertIsNotNone(reserialized_legacy.corner_brace_repair)

        closer = _corner("CB09", (0.0, 2800.0), (800.0, 2000.0), "P9")
        replay_base = replace(
            result,
            struts=(*result.struts, _strut("S3", 2000.0)),
            corner_braces=(*result.corner_braces, closer),
        )
        connections, messages = build_corner_brace_connections(replay_base)
        replay_base = replace(
            replay_base,
            corner_brace_connections=connections,
            messages=messages,
        )
        replayed, report = replay_manual_overrides(
            replay_base,
            (legacy_override,),
        )
        replayed_target = next(
            value for value in replayed.corner_braces if value.id == "CB71"
        )
        self.assertEqual(replayed_target.start, (0.0, 1000.0))
        self.assertEqual(replayed_target.end, (1000.0, 0.0))
        assert replayed_target.repair_provenance is not None
        self.assertIsNone(
            replayed_target.repair_provenance.selected_template_reference
        )
        self.assertTrue(
            any(value.endswith("CornerBrace repair") for value in report.preserved)
        )

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

    def test_new_replay_uses_saved_template_not_a_new_nearer_primary(self):
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
        closer = _corner("CB09", (0.0, 2800.0), (800.0, 2000.0), "P9")
        replay_base = replace(
            result,
            struts=(*result.struts, _strut("S3", 2000.0)),
            corner_braces=(*result.corner_braces, closer),
        )
        connections, messages = build_corner_brace_connections(replay_base)
        replay_base = replace(
            replay_base,
            corner_brace_connections=connections,
            messages=messages,
        )
        replayed, report = replay_manual_overrides(replay_base, overrides)
        replayed_target = next(value for value in replayed.corner_braces if value.id == "CB71")
        self.assertEqual(replayed_target.start, (0.0, 1000.0))
        assert replayed_target.repair_provenance is not None
        assert replayed_target.repair_provenance.selected_template_reference is not None
        self.assertEqual(
            replayed_target.repair_provenance.selected_template_reference.member_id,
            "CB10",
        )
        self.assertTrue(any(value.endswith("CornerBrace repair") for value in report.preserved))

    def test_new_replay_rejects_target_identity_or_template_connection_drift(self):
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
        changed_identity = replace(
            result,
            walers=tuple(
                replace(value, source_handles=("CHANGED",))
                if value.id == "W1"
                else value
                for value in result.walers
            ),
        )
        changed_connection = replace(
            result,
            corner_brace_connections=tuple(
                replace(
                    value,
                    baseline_waler_attachment=(
                        value.baseline_waler_attachment[0],
                        value.baseline_waler_attachment[1] + 100.0,
                    ),
                )
                if value.corner_brace_id == "CB10"
                else value
                for value in result.corner_brace_connections
            ),
        )
        for replay_base in (changed_identity, changed_connection):
            with self.subTest(replay_base=replay_base):
                replayed, report = replay_manual_overrides(replay_base, overrides)
                replayed_target = next(
                    value for value in replayed.corner_braces if value.id == "CB71"
                )
                self.assertIsNone(replayed_target.repair_provenance)
                self.assertTrue(
                    any(
                        value.endswith("CornerBrace repair")
                        for value in report.needs_review
                    )
                )

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
        assert repair_override.corner_brace_repair is not None
        self.assertIsNotNone(
            repair_override.corner_brace_repair.selected_template_reference
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
