import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import ezdxf

from bracing_optimizer.infrastructure.project_persistence import (
    DXF_AMBIGUITY_TOLERANCE_MM,
    DXF_GEOMETRY_TOLERANCE_MM,
)
from dxf_import.models import SourceManualOverride
from dxf_import.importer import DXFImporter
from dxf_import.dialog import (
    confirm_review_recovery,
    format_review_recovery_summary,
)
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.source_exclusion import ManualReplayReport
from dxf_import.source_exclusion import source_file_fingerprint

from dxf_import.review_recovery import (
    CriticalMemberMatch,
    RecoveryCategory,
    RecoverySummary,
    RecoverySummaryEntry,
    ReviewRecoveryPlan,
    ReviewRecoveryResult,
    ReviewRecoveryStage,
    ReviewRecoveryStatus,
    match_critical_members,
    rebind_manual_overrides,
)
from dxf_import.review_recovery_planner import ReviewRecoveryPlanner


class ReviewRecoveryContractTests(unittest.TestCase):
    def entry(self, category, label):
        return RecoverySummaryEntry(
            category,
            "member",
            label,
            "TEST_REASON",
            f"{label} 說明",
        )

    def test_summary_counts_are_derived_from_entries(self):
        summary = RecoverySummary((
            self.entry(RecoveryCategory.PRESERVED, "W1"),
            self.entry(RecoveryCategory.PRESERVED, "S1"),
            self.entry(RecoveryCategory.REQUIRES_REVIEW, "S2"),
            self.entry(RecoveryCategory.DISABLED, "排除來源"),
        ))

        self.assertEqual(summary.counts[RecoveryCategory.PRESERVED], 2)
        self.assertEqual(summary.counts[RecoveryCategory.REQUIRES_REVIEW], 1)
        self.assertEqual(summary.counts[RecoveryCategory.DISABLED], 1)
        self.assertEqual(
            tuple(item.label for item in summary.entries_for("preserved")),
            ("W1", "S1"),
        )

    def test_stage_copies_recovered_state_without_mutating_input(self):
        recovered = {"converted": {"walers": [{"id": "W1"}]}}
        before = copy.deepcopy(recovered)
        stage = ReviewRecoveryStage(
            Path("candidate.dxf"),
            "ab",
            "cd",
            recovered,
            object(),
            RecoverySummary(),
        )

        recovered["converted"]["walers"][0]["id"] = "MUTATED"

        self.assertEqual(before, stage.copy_recovered_state())
        self.assertEqual(stage.candidate_fingerprint, "AB")
        self.assertEqual(stage.base_state_token, "CD")

    def test_disabled_summary_entry_does_not_modify_recovered_state(self):
        recovered = {"excluded_sources": [], "converted": {"walers": []}}
        summary = RecoverySummary((
            RecoverySummaryEntry(
                RecoveryCategory.DISABLED,
                "source_exclusion",
                "strut:OLD",
                "EXCLUSION_IDENTITY_MISSING",
                "舊排除決策只保留為摘要。",
            ),
        ))

        stage = ReviewRecoveryStage(
            Path("candidate.dxf"),
            "AB",
            "CD",
            recovered,
            object(),
            summary,
        )

        self.assertEqual(stage.copy_recovered_state(), recovered)
        self.assertEqual(
            stage.summary.counts[RecoveryCategory.DISABLED],
            1,
        )

    def test_compatible_result_requires_plan(self):
        with self.assertRaises(ValueError):
            ReviewRecoveryResult(
                ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
                None,
                RecoverySummary(),
            )

    def test_failure_result_rejects_plan(self):
        stage = ReviewRecoveryStage(
            Path("candidate.dxf"),
            "AB",
            "CD",
            {},
            object(),
            RecoverySummary(),
        )
        with self.assertRaises(ValueError):
            ReviewRecoveryResult(
                ReviewRecoveryStatus.INCOMPATIBLE_SOURCE,
                ReviewRecoveryPlan(stage),
                RecoverySummary(),
            )


class ReviewRecoveryPresentationTests(unittest.TestCase):
    def summary(self):
        return RecoverySummary((
            RecoverySummaryEntry(
                RecoveryCategory.PRESERVED,
                "material",
                "W1 材料",
                "PRESERVED",
                "材料已沿用。",
            ),
            RecoverySummaryEntry(
                RecoveryCategory.REQUIRES_REVIEW,
                "layer",
                "NEW",
                "REVIEW",
                "新圖層需檢查。",
            ),
            RecoverySummaryEntry(
                RecoveryCategory.DISABLED,
                "source_exclusion",
                "OLD",
                "DISABLED",
                "舊排除已停用。",
            ),
        ))

    def test_summary_formats_all_counts_and_reasons(self):
        text = format_review_recovery_summary(self.summary())

        self.assertIn("已保留：1 項", text)
        self.assertIn("需重新檢查：1 項", text)
        self.assertIn("已停用：1 項", text)
        self.assertIn("材料已沿用", text)
        self.assertIn("新圖層需檢查", text)
        self.assertIn("舊排除已停用", text)

    def test_confirmation_returns_explicit_accept_or_reject(self):
        calls = []

        accepted = confirm_review_recovery(
            None,
            self.summary(),
            askyesno=lambda *args, **kwargs: calls.append((args, kwargs)) or True,
        )
        rejected = confirm_review_recovery(
            None,
            self.summary(),
            askyesno=lambda *args, **kwargs: False,
        )

        self.assertTrue(accepted)
        self.assertFalse(rejected)
        self.assertEqual(len(calls), 1)


class CriticalMemberMatchingTests(unittest.TestCase):
    @staticmethod
    def member(
        identifier,
        *,
        start=(0.0, 0.0),
        end=(100.0, 0.0),
        layer="STRUCTURE",
        handles=(),
    ):
        return {
            "id": identifier,
            "world_start": start,
            "world_end": end,
            "source_layer": layer,
            "source_handles": list(handles),
        }

    @staticmethod
    def saved(*, walers=(), struts=(), braces=()):
        return {
            "converted": {
                "walers": list(walers),
                "struts": list(struts),
                "braces": list(braces),
            }
        }

    @staticmethod
    def candidate(*, walers=(), struts=(), braces=()):
        return SimpleNamespace(
            walers=tuple(walers),
            struts=tuple(struts),
            braces=tuple(braces),
        )

    def match(self, saved, candidate):
        return match_critical_members(
            saved,
            candidate,
            geometry_tolerance_mm=DXF_GEOMETRY_TOLERANCE_MM,
            ambiguity_tolerance_mm=DXF_AMBIGUITY_TOLERANCE_MM,
        )

    def test_shared_handle_precedes_other_geometry_evidence(self):
        saved = self.saved(
            walers=(self.member("W1", handles=("AA",)),),
        )
        candidate = self.candidate(
            walers=(
                self.member("NEW-NEAR", start=(0.01, 0.0), end=(100.01, 0.0)),
                self.member(
                    "NEW-HANDLE",
                    start=(4.0, 0.0),
                    end=(104.0, 0.0),
                    handles=("aa",),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertTrue(result.compatible)
        self.assertEqual(result.matches[0].candidate_id, "NEW-HANDLE")
        self.assertEqual(result.matches[0].match_kind, "shared_handle")
        self.assertEqual(
            tuple(item.candidate_id for item in result.additions),
            ("NEW-NEAR",),
        )

    def test_shared_handle_outside_geometry_tolerance_is_not_a_match(self):
        saved = self.saved(walers=(self.member("W1", handles=("AA",)),))
        candidate = self.candidate(
            walers=(
                self.member(
                    "FAR",
                    start=(DXF_GEOMETRY_TOLERANCE_MM + 0.01, 0.0),
                    end=(100.0 + DXF_GEOMETRY_TOLERANCE_MM + 0.01, 0.0),
                    handles=("AA",),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertEqual(result.missing_saved_ids, ("W1",))

    def test_geometry_fallback_prefers_same_layer(self):
        saved = self.saved(walers=(self.member("W1"),))
        candidate = self.candidate(
            walers=(
                self.member(
                    "OTHER-LAYER",
                    start=(0.1, 0.0),
                    end=(100.1, 0.0),
                    layer="OTHER",
                ),
                self.member(
                    "SAME-LAYER",
                    start=(4.0, 0.0),
                    end=(104.0, 0.0),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertEqual(result.matches[0].candidate_id, "SAME-LAYER")
        self.assertEqual(result.matches[0].match_kind, "geometry")

    def test_geometry_tolerance_boundary_is_inclusive(self):
        saved = self.saved(struts=(self.member("S1"),))
        candidate = self.candidate(
            struts=(
                self.member(
                    "NEW-S1",
                    start=(DXF_GEOMETRY_TOLERANCE_MM, 0.0),
                    end=(100.0 + DXF_GEOMETRY_TOLERANCE_MM, 0.0),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertTrue(result.compatible)
        self.assertAlmostEqual(
            result.matches[0].geometry_error_mm,
            DXF_GEOMETRY_TOLERANCE_MM,
        )

    def test_geometry_beyond_tolerance_marks_saved_member_missing(self):
        saved = self.saved(braces=(self.member("B1"),))
        candidate = self.candidate(
            braces=(
                self.member(
                    "NEW-B1",
                    start=(DXF_GEOMETRY_TOLERANCE_MM + 0.01, 0.0),
                    end=(100.0 + DXF_GEOMETRY_TOLERANCE_MM + 0.01, 0.0),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertFalse(result.compatible)
        self.assertEqual(result.missing_saved_ids, ("B1",))

    def test_equally_good_candidates_are_ambiguous(self):
        saved = self.saved(walers=(self.member("W1"),))
        candidate = self.candidate(
            walers=(
                self.member("A", start=(0.04, 0.0), end=(100.04, 0.0)),
                self.member(
                    "B",
                    start=(0.04 + DXF_AMBIGUITY_TOLERANCE_MM, 0.0),
                    end=(100.04 + DXF_AMBIGUITY_TOLERANCE_MM, 0.0),
                ),
            ),
        )

        result = self.match(saved, candidate)

        self.assertFalse(result.compatible)
        self.assertEqual(result.ambiguous_saved_ids, ("W1",))

    def test_roles_never_cross_match_and_candidate_additions_are_reported(self):
        saved = self.saved(walers=(self.member("W1", handles=("10",)),))
        candidate = self.candidate(
            struts=(self.member("S1", handles=("10",)),),
            braces=(self.member("B-NEW", handles=("20",)),),
        )

        result = self.match(saved, candidate)

        self.assertEqual(result.missing_saved_ids, ("W1",))
        self.assertEqual(
            tuple((item.role, item.candidate_id) for item in result.additions),
            (("strut", "S1"), ("brace", "B-NEW")),
        )

    def test_candidate_member_is_never_reused(self):
        saved = self.saved(
            struts=(
                self.member("S1", handles=("SHARED",)),
                self.member("S2", handles=("SHARED",)),
            )
        )
        candidate = self.candidate(
            struts=(self.member("ONLY", handles=("SHARED",)),)
        )

        result = self.match(saved, candidate)

        self.assertEqual(len(result.matches), 1)
        self.assertEqual(result.missing_saved_ids, ("S2",))


class ManualOverrideRebindTests(unittest.TestCase):
    def test_rebinds_all_manual_input_types_to_candidate_identity(self):
        override = SourceManualOverride(
            role="waler",
            source_handles=("OLD",),
            display_id="W1",
            has_material_spec=True,
            material_spec="H350",
            geometry_selection_source="cad_manual",
            world_start=(0.0, 0.0),
            world_end=(100.0, 0.0),
            has_waler_contact_input=True,
            original_backfill_mm=50.0,
            adopted_backfill_mm=60.0,
            original_waler_width_mm=300.0,
            adopted_waler_width_mm=350.0,
        )
        match = CriticalMemberMatch(
            "waler",
            "W1",
            "NW1",
            0,
            0,
            "geometry",
            1.0,
            ("OLD",),
            ("NEW",),
        )

        result = rebind_manual_overrides((override,), (match,))

        self.assertEqual(len(result.rebound), 1)
        rebound = result.rebound[0]
        self.assertEqual(rebound.source_handles, ("NEW",))
        self.assertEqual(rebound.material_spec, "H350")
        self.assertEqual(rebound.geometry_selection_source, "cad_manual")
        self.assertTrue(rebound.has_waler_contact_input)
        self.assertEqual(result.requires_review_labels, ())

    def test_missing_safe_mapping_requires_review_without_retargeting(self):
        override = SourceManualOverride(
            role="strut",
            source_handles=("OLD",),
            display_id="S1",
            has_material_spec=True,
            material_spec="H400",
            geometry_selection_source="manual_candidate_points",
            world_start=(0.0, 0.0),
            world_end=(100.0, 0.0),
        )

        result = rebind_manual_overrides((override,), ())

        self.assertEqual(result.rebound, ())
        self.assertEqual(
            result.requires_review_labels,
            ("S1 材料規格", "S1 STEP5 工程線"),
        )


class ReviewRecoveryPlannerTests(unittest.TestCase):
    class FakeImporter:
        def __init__(self, fingerprint="NEW", layers=("WALER", "STRUT", "NEW")):
            self.source_fingerprint = fingerprint
            self.layer_names = tuple(layers)

        def read(self):
            return self

    @staticmethod
    def member(identifier, handle, layer, y=0.0):
        return {
            "id": identifier,
            "world_start": (0.0, y),
            "world_end": (100.0, y),
            "source_layer": layer,
            "source_handles": (handle,),
        }

    def workflow_factory(
        self,
        candidate_result,
        captured,
        manual_report=None,
        preserve_confirmations=True,
    ):
        class FakeWorkflow:
            def __init__(
                inner_self,
                importer,
                path,
                *,
                initial_state,
                material_specs,
            ):
                captured["initial_state"] = copy.deepcopy(initial_state)
                captured["material_specs"] = tuple(material_specs)
                inner_self.initial_state = copy.deepcopy(initial_state)
                inner_self.world_result = None

            def recognize(inner_self, layer_roles):
                captured["recognized_roles"] = dict(layer_roles)
                inner_self.world_result = candidate_result

            def recognize_staged(
                inner_self,
                excluded_sources,
                manual_overrides,
                *,
                layer_roles,
            ):
                captured["excluded_sources"] = tuple(excluded_sources)
                captured["manual_overrides"] = tuple(manual_overrides)
                captured["staged_roles"] = dict(layer_roles)
                return candidate_result, manual_report or ManualReplayReport()

            def install_staged_recovery(
                inner_self,
                world_result,
                *,
                layer_roles,
                excluded_sources,
                double_support_decisions,
                review_confirmations,
                manual_replay_report,
            ):
                captured["double_support_decisions"] = dict(
                    double_support_decisions
                )
                inner_self.world_result = world_result
                inner_self.review_confirmations = (
                    dict(review_confirmations)
                    if preserve_confirmations
                    else {}
                )

            def serialize_review_state(
                inner_self,
                *,
                layer_roles,
                import_mode,
            ):
                return {
                    **copy.deepcopy(inner_self.initial_state),
                    "layer_classification": dict(layer_roles),
                    "import_mode": import_mode,
                    "converted": {"candidate": True},
                    "component_associations": ["candidate-association"],
                    "validation_messages": ["candidate-validation"],
                    "review_confirmations": dict(
                        inner_self.review_confirmations
                    ),
                }

        return FakeWorkflow

    def planner(
        self,
        candidate_result,
        captured,
        importer=None,
        manual_report=None,
        preserve_confirmations=True,
    ):
        return ReviewRecoveryPlanner(
            geometry_tolerance_mm=DXF_GEOMETRY_TOLERANCE_MM,
            ambiguity_tolerance_mm=DXF_AMBIGUITY_TOLERANCE_MM,
            importer_factory=lambda path: importer or self.FakeImporter(),
            workflow_factory=self.workflow_factory(
                candidate_result,
                captured,
                manual_report,
                preserve_confirmations,
            ),
        )

    def compatible_fixture(self):
        saved_waler = self.member("W1", "OLD-W", "WALER")
        saved_strut = self.member("S1", "OLD-S", "STRUT", 20.0)
        candidate = SimpleNamespace(
            walers=(self.member("NW1", "NEW-W", "WALER"),),
            struts=(self.member("NS1", "NEW-S", "STRUT", 20.0),),
            braces=(),
        )
        state = {
            "source_fingerprint": "OLD",
            "layer_classification": {
                "WALER": "waler",
                "STRUT": "strut",
                "GONE": "brace",
            },
            "coordinate_system": {
                "mode": "local",
                "origin_x": 12.5,
                "origin_y": -7.25,
                "source": "selected_candidate_point",
            },
            "import_mode": "append",
            "converted": {
                "walers": [saved_waler],
                "struts": [saved_strut],
                "braces": [],
            },
            "component_associations": ["old-association"],
            "validation_messages": ["old-validation"],
            "candidate_points": ["old-candidate"],
        }
        return state, candidate

    def test_candidate_recognition_reuses_only_safe_settings(self):
        state, candidate = self.compatible_fixture()
        captured = {}

        result = self.planner(candidate, captured).plan(
            "candidate.dxf",
            "NEW",
            state,
            "BASE",
        )

        self.assertEqual(
            result.status,
            ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertEqual(
            captured["recognized_roles"],
            {"WALER": "waler", "STRUT": "strut", "NEW": "ignore"},
        )
        initial = captured["initial_state"]
        self.assertEqual(initial["coordinate_system"]["mode"], "local")
        self.assertEqual(initial["coordinate_system"]["origin_x"], 12.5)
        self.assertEqual(initial["import_mode"], "append")
        self.assertNotIn("converted", initial)
        self.assertNotIn("component_associations", initial)
        self.assertNotIn("validation_messages", initial)
        self.assertNotIn("candidate_points", initial)

        recovered = result.plan.stage.copy_recovered_state()
        self.assertEqual(recovered["converted"], {"candidate": True})
        self.assertEqual(
            recovered["component_associations"],
            ["candidate-association"],
        )
        reasons = {entry.reason_code for entry in result.summary.entries}
        self.assertIn("CANDIDATE_LAYER_UNSEEN", reasons)
        self.assertIn("SAVED_LAYER_MISSING", reasons)

    def test_invalid_coordinate_and_import_mode_use_safe_fallbacks(self):
        state, candidate = self.compatible_fixture()
        state["coordinate_system"] = {
            "mode": "local",
            "origin_x": float("nan"),
            "origin_y": 1.0,
        }
        state["import_mode"] = "overwrite-everything"
        captured = {}

        result = self.planner(candidate, captured).plan(
            "candidate.dxf",
            "NEW",
            state,
            "BASE",
        )

        self.assertEqual(
            result.status,
            ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertEqual(
            captured["initial_state"]["coordinate_system"]["mode"],
            "world",
        )
        self.assertEqual(captured["initial_state"]["import_mode"], "replace")
        reasons = {entry.reason_code for entry in result.summary.entries}
        self.assertIn("COORDINATE_SYSTEM_FALLBACK", reasons)
        self.assertIn("IMPORT_MODE_FALLBACK", reasons)

    def test_manual_inputs_are_rebound_then_classified_from_replay_report(self):
        state, candidate = self.compatible_fixture()
        state["manual_overrides"] = [{
            "role": "waler",
            "source_handles": ["OLD-W"],
            "display_id": "W1",
            "has_material_spec": True,
            "material_spec": "H350",
            "geometry_selection_source": "cad_manual",
            "world_start": [0.0, 0.0],
            "world_end": [100.0, 0.0],
            "has_waler_contact_input": True,
            "original_backfill_mm": 50.0,
            "adopted_backfill_mm": 60.0,
            "original_waler_width_mm": 300.0,
            "adopted_waler_width_mm": 350.0,
        }]
        captured = {}
        report = ManualReplayReport(
            preserved=("W1 材料規格", "W1 CAD 工程線"),
            needs_review=("W1 Waler 背填／寬度",),
        )

        result = self.planner(
            candidate,
            captured,
            manual_report=report,
        ).plan("candidate.dxf", "NEW", state, "BASE")

        self.assertEqual(
            result.status,
            ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
        )
        self.assertEqual(
            captured["manual_overrides"][0].source_handles,
            ("NEW-W",),
        )
        by_label = {entry.label: entry.category for entry in result.summary.entries}
        self.assertEqual(
            by_label["W1 材料規格"],
            RecoveryCategory.PRESERVED,
        )
        self.assertEqual(
            by_label["W1 CAD 工程線"],
            RecoveryCategory.PRESERVED,
        )
        self.assertEqual(
            by_label["W1 Waler 背填／寬度"],
            RecoveryCategory.REQUIRES_REVIEW,
        )

    def test_manual_replay_disabled_report_is_recovery_requires_review(self):
        state, candidate = self.compatible_fixture()
        state["manual_overrides"] = [{
            "role": "strut",
            "source_handles": ["OLD-S"],
            "display_id": "S1",
            "has_material_spec": True,
            "material_spec": "H400",
        }]
        captured = {}

        result = self.planner(
            candidate,
            captured,
            manual_report=ManualReplayReport(disabled=("S1 材料規格",)),
        ).plan("candidate.dxf", "NEW", state, "BASE")

        manual_entry = next(
            entry for entry in result.summary.entries
            if entry.label == "S1 材料規格"
        )
        self.assertEqual(
            manual_entry.category,
            RecoveryCategory.REQUIRES_REVIEW,
        )

    def test_exclusion_requires_exact_same_role_identity(self):
        state, candidate = self.compatible_fixture()
        state["excluded_sources"] = [{
            "role": "strut",
            "source_handles": ["EXACT"],
            "display_id_when_excluded": "待修-EXACT",
        }]
        candidate.source_geometry = (
            SimpleNamespace(role="strut", source_handle="exact"),
        )
        captured = {}

        result = self.planner(candidate, captured).plan(
            "candidate.dxf", "NEW", state, "BASE"
        )

        self.assertEqual(len(captured["excluded_sources"]), 1)
        entry = next(
            item for item in result.summary.entries
            if item.subject_kind == "source_exclusion"
        )
        self.assertEqual(entry.category, RecoveryCategory.PRESERVED)

    def test_geometry_member_match_never_transfers_changed_exclusion(self):
        state, candidate = self.compatible_fixture()
        state["excluded_sources"] = [{
            "role": "waler",
            "source_handles": ["OLD-EXCLUDED"],
            "display_id_when_excluded": "W-OLD",
        }]
        candidate.source_geometry = (
            SimpleNamespace(role="waler", source_handle="NEW-EXCLUDED"),
        )
        captured = {}

        result = self.planner(candidate, captured).plan(
            "candidate.dxf", "NEW", state, "BASE"
        )

        self.assertEqual(captured["excluded_sources"], ())
        entry = next(
            item for item in result.summary.entries
            if item.subject_kind == "source_exclusion"
        )
        self.assertEqual(entry.category, RecoveryCategory.DISABLED)
        self.assertEqual(
            result.plan.stage.copy_recovered_state().get("excluded_sources", []),
            [],
        )

    def double_support_fixture(self, *, include_candidate_pair):
        old_a = self.member("S1", "OLD-A", "STRUT", 0.0)
        old_b = self.member("S2", "OLD-B", "STRUT", 20.0)
        new_a = SimpleNamespace(
            id="NS1",
            world_start=(0.0, 0.0),
            world_end=(100.0, 0.0),
            source_layer="STRUT",
            source_handles=("NEW-A",),
        )
        new_b = SimpleNamespace(
            id="NS2",
            world_start=(0.0, 20.0),
            world_end=(100.0, 20.0),
            source_layer="STRUT",
            source_handles=("NEW-B",),
        )
        pair = SimpleNamespace(first_strut_id="NS1", second_strut_id="NS2")
        candidate = SimpleNamespace(
            walers=(),
            struts=(new_a, new_b),
            braces=(),
            double_support_candidates=((pair,) if include_candidate_pair else ()),
        )
        state = {
            "layer_classification": {
                "WALER": "waler",
                "STRUT": "strut",
            },
            "coordinate_system": {"mode": "world"},
            "import_mode": "replace",
            "converted": {
                "walers": [],
                "struts": [old_a, old_b],
                "braces": [],
            },
            "double_support_decisions": [{
                "first_source_handles": ["OLD-A"],
                "second_source_handles": ["OLD-B"],
                "accepted": False,
            }],
        }
        return state, candidate

    def test_double_support_decision_rebinds_only_to_unique_candidate_pair(self):
        state, candidate = self.double_support_fixture(
            include_candidate_pair=True
        )
        captured = {}
        importer = self.FakeImporter(layers=("WALER", "STRUT"))

        result = self.planner(candidate, captured, importer=importer).plan(
            "candidate.dxf", "NEW", state, "BASE"
        )

        self.assertEqual(
            captured["double_support_decisions"],
            {(('NEW-A',), ('NEW-B',)): False},
        )
        entry = next(
            item for item in result.summary.entries
            if item.subject_kind == "double_support"
        )
        self.assertEqual(entry.category, RecoveryCategory.PRESERVED)

    def test_missing_double_support_pair_requires_review(self):
        state, candidate = self.double_support_fixture(
            include_candidate_pair=False
        )
        captured = {}
        importer = self.FakeImporter(layers=("WALER", "STRUT"))

        result = self.planner(candidate, captured, importer=importer).plan(
            "candidate.dxf", "NEW", state, "BASE"
        )

        self.assertEqual(captured["double_support_decisions"], {})
        entry = next(
            item for item in result.summary.entries
            if item.subject_kind == "double_support"
        )
        self.assertEqual(entry.category, RecoveryCategory.REQUIRES_REVIEW)

    def test_confirmation_is_preserved_only_when_current_signature_is_valid(self):
        state, candidate = self.compatible_fixture()
        state["review_confirmations"] = {"waler:OLD-W": "ABC123"}
        captured = {}

        preserved = self.planner(candidate, captured).plan(
            "candidate.dxf", "NEW", state, "BASE"
        )

        preserved_entry = next(
            item for item in preserved.summary.entries
            if item.subject_kind == "confirmation"
        )
        self.assertEqual(
            preserved_entry.category,
            RecoveryCategory.PRESERVED,
        )
        self.assertEqual(
            preserved.plan.stage.copy_recovered_state()["review_confirmations"],
            {"waler:NEW-W": "ABC123"},
        )

        captured = {}
        invalid = self.planner(
            candidate,
            captured,
            preserve_confirmations=False,
        ).plan("candidate.dxf", "NEW", state, "BASE")

        invalid_entry = next(
            item for item in invalid.summary.entries
            if item.subject_kind == "confirmation"
        )
        self.assertEqual(
            invalid_entry.category,
            RecoveryCategory.REQUIRES_REVIEW,
        )
        self.assertEqual(
            invalid.plan.stage.copy_recovered_state()["review_confirmations"],
            {},
        )

    def test_candidate_fingerprint_change_fails_without_recognition(self):
        state, candidate = self.compatible_fixture()
        captured = {}

        result = self.planner(
            candidate,
            captured,
            importer=self.FakeImporter(fingerprint="CHANGED"),
        ).plan("candidate.dxf", "EXPECTED", state, "BASE")

        self.assertEqual(result.status, ReviewRecoveryStatus.VALIDATION_FAILED)
        self.assertNotIn("recognized_roles", captured)

    def test_recognition_failure_returns_validation_failed(self):
        state, candidate = self.compatible_fixture()
        captured = {}
        base_factory = self.workflow_factory(candidate, captured)

        class FailingWorkflow(base_factory):
            def recognize(self, layer_roles):
                raise ValueError("recognition failed")

        planner = ReviewRecoveryPlanner(
            geometry_tolerance_mm=DXF_GEOMETRY_TOLERANCE_MM,
            ambiguity_tolerance_mm=DXF_AMBIGUITY_TOLERANCE_MM,
            importer_factory=lambda path: self.FakeImporter(),
            workflow_factory=FailingWorkflow,
        )

        result = planner.plan("candidate.dxf", "NEW", state, "BASE")

        self.assertEqual(result.status, ReviewRecoveryStatus.VALIDATION_FAILED)
        self.assertIn("recognition failed", result.detail_lines)


class ReviewRecoveryIntegrationTests(unittest.TestCase):
    @staticmethod
    def write_source(path, *, add_unseen_layer=False):
        document = ezdxf.new("R2018")
        document.layers.add("WALER")
        document.layers.add("STRUT")
        model = document.modelspace()
        model.add_line(
            (0.0, 0.0),
            (1000.0, 0.0),
            dxfattribs={"layer": "WALER"},
        )
        model.add_line(
            (500.0, 0.0),
            (500.0, 1000.0),
            dxfattribs={"layer": "STRUT"},
        )
        if add_unseen_layer:
            document.layers.add("NEW-NOTES")
            model.add_line(
                (0.0, 2000.0),
                (1000.0, 2000.0),
                dxfattribs={"layer": "NEW-NOTES"},
            )
        document.saveas(path)

    def test_real_candidate_rebuild_serializes_version_two_candidate_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            saved_path = root / "saved.dxf"
            candidate_path = root / "candidate.dxf"
            self.write_source(saved_path)
            self.write_source(candidate_path, add_unseen_layer=True)

            importer = DXFImporter(saved_path).read()
            initial_state = {
                "source_path": str(saved_path),
                "source_fingerprint": importer.source_fingerprint,
                "layer_classification": {
                    "WALER": "waler",
                    "STRUT": "strut",
                },
                "coordinate_system": {"mode": "world"},
                "import_mode": "replace",
            }
            workflow = DXFReviewWorkflow(
                importer,
                saved_path,
                initial_state=initial_state,
            )
            workflow.recognize(initial_state["layer_classification"])
            saved_state = workflow.serialize_review_state()

            planner = ReviewRecoveryPlanner(
                geometry_tolerance_mm=DXF_GEOMETRY_TOLERANCE_MM,
                ambiguity_tolerance_mm=DXF_AMBIGUITY_TOLERANCE_MM,
            )
            candidate_fingerprint = source_file_fingerprint(candidate_path)

            recovery = planner.plan(
                candidate_path,
                candidate_fingerprint,
                saved_state,
                "BASE-TOKEN",
            )

            self.assertEqual(
                recovery.status,
                ReviewRecoveryStatus.COMPATIBLE_RECOVERY_AVAILABLE,
                recovery.detail_lines,
            )
            stage = recovery.plan.stage
            recovered_state = stage.copy_recovered_state()
            self.assertEqual(recovered_state["review_state_version"], 2)
            self.assertEqual(
                recovered_state["source_path"],
                str(candidate_path.resolve()),
            )
            self.assertEqual(
                recovered_state["source_fingerprint"],
                candidate_fingerprint,
            )
            self.assertEqual(
                recovered_state["converted"],
                stage.world_result.to_debug_dict()["converted"],
            )
            self.assertEqual(
                recovered_state["component_associations"],
                stage.world_result.to_debug_dict()["component_associations"],
            )
            self.assertNotIn("recovery_summary", recovered_state)
            self.assertNotIn("recovery_plan", recovered_state)
            unseen = next(
                entry for entry in recovery.summary.entries
                if entry.label == "NEW-NOTES"
            )
            self.assertEqual(
                unseen.category,
                RecoveryCategory.REQUIRES_REVIEW,
            )


if __name__ == "__main__":
    unittest.main()
