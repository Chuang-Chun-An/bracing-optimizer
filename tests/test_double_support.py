import unittest
import copy
from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bracing_optimizer.algorithms import solver_search, support
from bracing_optimizer.application.optimize_support_zone import (
    OptimizeSupportZone,
    OptimizeSupportZoneRequest,
)
from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.solver_input_builder import (
    SupportAdjacencyContract,
    SupportInputBuilder,
    SupportOptimizationUnit,
    SupportZoneInput,
)
from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from dxf_import.candidate_points import (
    ambiguous_column_repair_options,
    associate_components_to_struts,
    column_association_options,
    rebuild_component_associations,
)
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter, Y29_LAYER_MAPPING
from dxf_import.models import (
    Column,
    ColumnAssociationDecision,
    DoubleSupportCandidate,
    DXFImportResult,
    ExcludedSource,
    GeometryTolerances,
    Strut,
    StrutTerminalTopology,
)
from dxf_import.review_workflow import DXFReviewWorkflow
from dxf_import.support_pairing import (
    apply_double_support_decisions,
    detect_double_support_candidates,
    double_support_candidate_identity,
    double_support_decisions_from_review_state,
    preserve_double_support_result_decisions,
    serialize_double_support_decisions,
    set_double_support_candidate_accepted,
)
from dxf_import.validation import build_problem_records, build_review_items


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def support_plan(
    support_id,
    *,
    pieces,
    jack_center,
    shared_layout_group="",
    score=0,
):
    return support.SupportPlan(
        support_id=support_id,
        pieces=list(pieces),
        joints=[],
        gap=0,
        jack_center=jack_center,
        jack_region_id=1,
        score=score,
        valid=True,
        material_spec="H350",
        shared_layout_group=shared_layout_group,
    )


def dxf_strut(identifier, start, end, *, from_waler="W1", to_waler="W2"):
    return Strut(
        id=identifier,
        start=start,
        end=end,
        source_layer="STRUT",
        source_handles=(identifier,),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=350,
        from_waler=from_waler,
        to_waler=to_waler,
        confidence=1.0,
    )


def dxf_column(identifier, reference, *, source_width=400):
    x, y = reference
    return Column(
        id=identifier,
        start=(x - source_width / 2, y),
        end=(x + source_width / 2, y),
        source_layer="COLUMN",
        source_handles=(identifier,),
        source_entity_types=("INSERT",),
        recognition_method="block_reference",
        centerline_computed=True,
        source_width=source_width,
        confidence=1.0,
        reference_point=reference,
        world_reference_point=reference,
    )


def dxf_result(struts, columns, candidates):
    return DXFImportResult(
        source_path="drawing.dxf",
        layer_names=("STRUT", "COLUMN"),
        selected_layers={"strut": ("STRUT",), "column": ("COLUMN",)},
        layer_info=(),
        walers=(),
        struts=tuple(struts),
        braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={"strut": len(struts), "column": len(columns)},
        columns=tuple(columns),
        double_support_candidates=tuple(candidates),
    )


class DoubleSupportSolverTests(unittest.TestCase):
    def test_group_members_may_share_the_same_jack_center(self):
        pieces = (("steel", 4000), ("jack", 600), ("steel", 5400))
        first = support_plan(
            "S1-A",
            pieces=pieces,
            jack_center=4300,
            shared_layout_group="G1",
        )
        second = support_plan(
            "S1-B",
            pieces=pieces,
            jack_center=4300,
            shared_layout_group="G1",
        )

        solution = support.build_global_solution([[first], [second]])

        self.assertTrue(solution.valid)
        self.assertEqual(len(solution.plans), 2)
        self.assertIsNone(solution.min_jack_distance)
        self.assertEqual(
            support.support_steel_lengths(solution.plans),
            [4000, 5400, 4000, 5400],
        )

    def test_group_members_cannot_select_different_layouts(self):
        first = support_plan(
            "S1-A",
            pieces=(("steel", 4000), ("jack", 600)),
            jack_center=4300,
            shared_layout_group="G1",
        )
        second = support_plan(
            "S1-B",
            pieces=(("steel", 5000), ("jack", 600)),
            jack_center=5300,
            shared_layout_group="G1",
        )

        solution = support.build_global_solution([[first], [second]])

        self.assertFalse(solution.valid)

    def test_incomplete_group_is_not_a_valid_global_solution(self):
        plan = support_plan(
            "S1-A",
            pieces=(("steel", 4000), ("jack", 600)),
            jack_center=4300,
            shared_layout_group="G1",
        )

        self.assertFalse(support.make_global_solution([plan]).valid)

    def test_ordinary_supports_still_obey_jack_spacing(self):
        first = support_plan("S1", pieces=(("jack", 600),), jack_center=300)
        second = support_plan("S2", pieces=(("jack", 600),), jack_center=300)

        self.assertFalse(support.pair_penalty(first, second)[0])

    def test_use_case_keeps_only_layouts_shared_by_both_group_members(self):
        configs = tuple(
            support.SupportConfig(
                support_id=support_id,
                total_length=10_000,
                pile_centers=[],
                waler_centers=[],
                material_spec="H350",
                steel_lengths=[4_000, 4_400, 5_000, 5_400],
                shared_layout_group="G1",
            )
            for support_id in ("S1-A", "S1-B")
        )
        common = (("steel", 4000), ("jack", 600), ("steel", 5400))
        only_first = (("steel", 5000), ("jack", 600), ("steel", 4400))
        only_second = (("steel", 4400), ("jack", 600), ("steel", 5000))

        def candidates_for_config(*, config, **_kwargs):
            layouts = (
                (common, only_first)
                if config.support_id == "S1-A"
                else (common, only_second)
            )
            return [
                support_plan(
                    "template",
                    pieces=pieces,
                    jack_center=4300,
                    shared_layout_group="G1",
                    score=index,
                )
                for index, pieces in enumerate(layouts)
            ]

        policy = replace(
            solver_search.DEFAULT_SEARCH_POLICY,
            support_global_search_stages=(
                solver_search.SupportGlobalSearchStage("TEST", beam_width=10),
            ),
            minimum_unique_solution_count=1,
            support_phase1_retained_candidate_count=1,
        )
        unit = SupportOptimizationUnit(
            unit_id="G1",
            configs=configs,
            require_shared_layout=True,
            member_ids=tuple(config.support_id for config in configs),
        )
        request = OptimizeSupportZoneRequest(
            input=SupportZoneInput(
                "Z1",
                configs,
                SupportAdjacencyContract(
                    zoning="Z1",
                    common_direction=(1.0, 0.0),
                    row_direction=(0.0, 1.0),
                    ordered_units=(unit,),
                    pairs=(),
                ),
            ),
            material_ratio_targets=MaterialRatioTargets.normalized(1, 0, 0),
            material_ratio_weight=0,
        )

        with (
            patch(
                "bracing_optimizer.application.optimize_support_zone.support."
                "build_support_candidate_cache_key",
                autospec=True,
                side_effect=lambda config, **_kwargs: (config.support_id,),
            ),
            patch(
                "bracing_optimizer.application.optimize_support_zone.support."
                "generate_single_support_candidates",
                autospec=True,
                side_effect=candidates_for_config,
            ),
        ):
            result = OptimizeSupportZone({}, search_policy=policy).execute(request)

        self.assertIsNotNone(result.solution)
        self.assertTrue(result.solution.valid)
        self.assertEqual(len(result.solution.plans), 2)
        self.assertEqual(
            [tuple(plan.pieces) for plan in result.solution.plans],
            [common, common],
        )


class DoubleSupportInputTests(unittest.TestCase):
    def test_builder_groups_members_with_one_shared_direction(self):
        project = ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "RC"},
                {"WalerID": "W2", "material_spec": "H350"},
            ],
            struts=[
                {
                    "StrutID": "S1-A",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 10000,
                    "EndY": 0,
                    "ColumnPositions": "3000",
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
                {
                    "StrutID": "S1-B",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "StartX": 0,
                    "StartY": 1000,
                    "EndX": 10000,
                    "EndY": 1000,
                    "ColumnPositions": "3000",
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
            ],
            inventory=[{
                "ItemCode": "S-50",
                "Spec": "H350",
                "Usage": "支撐",
                "Length": 5000,
                "Qty": 4,
            }],
        )

        result = SupportInputBuilder().build_zone(project, "Z1")

        self.assertEqual(len(result.units), 1)
        self.assertTrue(result.units[0].require_shared_layout)
        self.assertEqual(
            [config.shared_layout_group for config in result.configs],
            ["G1", "G1"],
        )
        self.assertEqual(result.configs[1].pile_centers, [3000])
        self.assertEqual(result.configs[1].from_waler_type, "RC")
        self.assertEqual(result.configs[1].to_waler_type, "Steel")

    def test_builder_unions_group_columns_without_mutating_project(self):
        project = ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "RC"},
                {"WalerID": "W2", "material_spec": "H350"},
            ],
            struts=[
                {
                    "StrutID": "S1",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 10000,
                    "EndY": 0,
                    "ColumnPositions": "3000,7000",
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
                {
                    "StrutID": "S2",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "StartX": 0,
                    "StartY": 1000,
                    "EndX": 10000,
                    "EndY": 1000,
                    "ColumnPositions": "3000.4,5000",
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
            ],
        )
        before = copy.deepcopy(project.to_case_data())

        result = SupportInputBuilder().build_zone(project, "Z1")

        self.assertEqual(
            [config.pile_centers for config in result.configs],
            [[3000, 5000, 7000], [3000, 5000, 7000]],
        )
        cache_keys = [
            support.build_support_candidate_cache_key(
                config,
                max_length_combinations=10,
                min_candidates=5,
                beam_width=10,
                max_layouts_per_combo=10,
            )
            for config in result.configs
        ]
        self.assertEqual(cache_keys[0], cache_keys[1])
        self.assertEqual(project.to_case_data(), before)

    def test_builder_does_not_union_columns_across_ordinary_supports(self):
        project = ProjectDataModel(
            struts=[
                {
                    "StrutID": "S1",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 10000,
                    "EndY": 0,
                    "ColumnPositions": "3000",
                    "Zoning": "Z1",
                },
                {
                    "StrutID": "S2",
                    "StartX": 0,
                    "StartY": 1000,
                    "EndX": 10000,
                    "EndY": 1000,
                    "ColumnPositions": "5000",
                    "Zoning": "Z1",
                },
            ],
        )

        result = SupportInputBuilder().build_zone(project, "Z1")

        self.assertEqual(
            [config.pile_centers for config in result.configs],
            [[3000], [5000]],
        )

    def test_reversed_dxf_stations_are_aligned_before_builder_union(self):
        first = replace(
            dxf_strut("S1", (0, 0), (10000, 0)),
            column_positions=(3000,),
            associated_columns=("C1",),
        )
        second = replace(
            dxf_strut(
                "S2",
                (10000, 1000),
                (0, 1000),
                from_waler="W2",
                to_waler="W1",
            ),
            column_positions=(7000,),
            associated_columns=("C1",),
        )
        import_result = dxf_result(
            (first, second),
            (),
            detect_double_support_candidates((first, second)),
        )
        rows = import_result.to_project_rows()["struts"]
        project = ProjectDataModel(
            walers=[{"WalerID": "W1"}, {"WalerID": "W2"}],
            struts=rows,
        )

        result = SupportInputBuilder().build_zone(project, "DXF")

        self.assertEqual(
            [config.pile_centers for config in result.configs],
            [[3000], [3000]],
        )

    def test_builder_rejects_opposite_group_directions(self):
        project = ProjectDataModel(
            walers=[
                {"WalerID": "W1", "material_spec": "RC"},
                {"WalerID": "W2", "material_spec": "H350"},
            ],
            struts=[
                {
                    "StrutID": "S1-A",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W1",
                    "ToWaler": "W2",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 10000,
                    "EndY": 0,
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
                {
                    "StrutID": "S1-B",
                    "SharedLayoutGroup": "G1",
                    "FromWaler": "W2",
                    "ToWaler": "W1",
                    "StartX": 10000,
                    "StartY": 1000,
                    "EndX": 0,
                    "EndY": 1000,
                    "Zoning": "Z1",
                    "material_spec": "H350",
                },
            ],
        )

        with self.assertRaisesRegex(Exception, "相同圍令方向"):
            SupportInputBuilder().build_zone(project, "Z1")


class DoubleSupportDXFTests(unittest.TestCase):
    def test_column_decision_uses_exact_source_identities(self):
        decision = ColumnAssociationDecision(
            column_source_handles=("c25",),
            candidate_strut_sources=(("s35",), ("s20",)),
            selected_strut_sources=(("s35",),),
            source_fingerprint="fingerprint",
            column_display_id="C25",
        )
        self.assertEqual(decision.column_source_handles, ("C25",))
        self.assertEqual(decision.candidate_strut_sources, (("S20",), ("S35",)))
        self.assertEqual(decision.selected_strut_sources, (("S35",),))
        with self.assertRaises(ValueError):
            ColumnAssociationDecision(
                column_source_handles=("C25",),
                candidate_strut_sources=(("S20",), ("S35",)),
                selected_strut_sources=(("S36",),),
                source_fingerprint="fingerprint",
            )

    def test_column_repair_requires_exactly_two_unshared_nearby_options(self):
        column = dxf_column("C1", (3000, 498.5))
        first = dxf_strut("S1", (0, 0), (10000, 0))
        second = dxf_strut("S2", (0, 1000), (10000, 1000))
        eligible = ambiguous_column_repair_options(column, (second, first))
        self.assertEqual([item[1] for item in eligible.options], ["S1", "S2"])
        self.assertEqual(eligible.reason, "")
        self.assertEqual(
            eligible,
            ambiguous_column_repair_options(column, (first, second)),
        )

        crowded_column = dxf_column("C2", (3000, 500))
        crowded = (
            first,
            dxf_strut("S3", (0, 10), (10000, 10)),
            dxf_strut("S4", (0, 20), (10000, 20)),
        )
        self.assertEqual(
            ambiguous_column_repair_options(crowded_column, crowded).reason,
            "multiple_nearby_struts",
        )
        accepted = detect_double_support_candidates((first, second))
        self.assertEqual(
            ambiguous_column_repair_options(
                column,
                (first, second),
                double_support_candidates=accepted,
            ).reason,
            "accepted_double_support",
        )

        opposite = dxf_strut("S5", (0, -1000), (10000, -1000))
        conflicting = tuple(
            replace(candidate, accepted=True)
            for candidate in detect_double_support_candidates((first, second, opposite))
        )
        self.assertEqual(
            ambiguous_column_repair_options(
                column,
                (first, second, opposite),
                double_support_candidates=conflicting,
            ).reason,
            "conflicting_accepted_groups",
        )

    def test_column_options_use_finite_axes_and_include_tolerance_boundary(self):
        column = dxf_column("C1", (3000, 500))
        forward = dxf_strut("S1", (0, 0), (10000, 0))
        reverse = dxf_strut("S2", (10000, 1000), (0, 1000))
        beyond = dxf_strut("S3", (4000, 500), (5000, 500))
        options = column_association_options(column, (reverse, beyond, forward))
        self.assertEqual([item[1] for item in options], ["S1", "S2"])
        self.assertAlmostEqual(options[0][0], 500)
        self.assertAlmostEqual(options[0][2], 3000)
        self.assertAlmostEqual(options[1][2], 7000)

        limit = GeometryTolerances(maximum_column_association_tolerance_mm=500)
        self.assertEqual(len(column_association_options(column, (forward, reverse), limit)), 2)

    @staticmethod
    def _with_terminal_topology(
        strut,
        *,
        start=("WA",),
        end=("WB",),
        start_issue=None,
    ):
        facts = [
            StrutTerminalTopology("end", tuple(end)),
        ]
        if start_issue is None:
            facts.append(StrutTerminalTopology("start", tuple(start)))
        else:
            facts.append(
                StrutTerminalTopology(
                    "start",
                    reason_code="AMBIGUOUS_WALER_CONNECTION",
                    competing_waler_source_handles=tuple(start_issue),
                    message="端點有多個合法圍令來源。",
                )
            )
        return replace(
            strut,
            terminal_topology_authoritative=True,
            terminal_topology=tuple(facts),
        )

    def test_parallel_struts_at_1000_mm_become_one_candidate(self):
        candidates = detect_double_support_candidates((
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        ))

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].accepted)
        self.assertAlmostEqual(candidates[0].centerline_spacing, 1000)
        self.assertGreaterEqual(candidates[0].overlap_ratio, 0.9)

    def test_geometry_qualification_keeps_pending_and_incompatible_outcomes(self):
        first = self._with_terminal_topology(
            dxf_strut("S1", (0, 0), (10000, 0))
        )
        pending = self._with_terminal_topology(
            dxf_strut("S2", (0, 1000), (10000, 1000)),
            start_issue=(("WA",), ("WC",)),
        )
        incompatible = self._with_terminal_topology(
            dxf_strut("S3", (0, 1000), (10000, 1000)),
            start=("WX",),
            end=("WY",),
        )

        pending_candidate = detect_double_support_candidates((first, pending))[0]
        missing = replace(
            pending,
            terminal_topology=(StrutTerminalTopology("end", ("WB",)),),
        )
        missing_candidate = detect_double_support_candidates((first, missing))[0]
        incompatible_candidate = detect_double_support_candidates(
            (first, incompatible)
        )[0]

        self.assertEqual(pending_candidate.qualification_status, "pending_waler")
        self.assertFalse(pending_candidate.accepted)
        self.assertEqual(pending_candidate.issues[0].terminal_name, "start")
        self.assertEqual(
            set(pending_candidate.issues[0].competing_waler_source_handles),
            {("WA",), ("WC",)},
        )
        self.assertEqual(missing_candidate.qualification_status, "pending_waler")
        self.assertEqual(
            missing_candidate.issues[0].code,
            "DOUBLE_SUPPORT_WALER_TERMINAL_MISSING",
        )
        self.assertEqual(
            incompatible_candidate.qualification_status,
            "incompatible_waler",
        )
        self.assertFalse(incompatible_candidate.accepted)

    def test_unreliable_axis_and_column_evidence_cannot_create_pair(self):
        first = replace(
            dxf_strut("S1", (0, 0), (10000, 0)),
            source_axis_supported=False,
        )
        second = dxf_strut("S2", (0, 1000), (10000, 1000))

        self.assertEqual(detect_double_support_candidates((first, second)), ())

        outside = dxf_strut("S3", (0, 1200), (10000, 1200))
        self.assertEqual(
            detect_double_support_candidates((second, outside)),
            (),
        )

    def test_all_numeric_equality_boundaries_are_inclusive(self):
        tolerances = GeometryTolerances()
        radians = math.radians(tolerances.parallel_angle_tolerance_deg)
        half_axis = (5000 * math.cos(radians), 5000 * math.sin(radians))
        cases = (
            (
                dxf_strut("S1", (0, 0), (10000, 0)),
                dxf_strut("S2", (0, 1150), (10000, 1150)),
            ),
            (
                dxf_strut("S1", (0, 0), (10000, 0)),
                dxf_strut("S2", (1000, 1000), (11000, 1000)),
            ),
            (
                dxf_strut("S1", (0, 0), (10000, 0)),
                dxf_strut("S2", (0, 1000), (9750, 1000)),
            ),
            (
                dxf_strut("S1", (0, 0), (10000, 0)),
                dxf_strut(
                    "S2",
                    (5000 - half_axis[0], 1000 - half_axis[1]),
                    (5000 + half_axis[0], 1000 + half_axis[1]),
                ),
            ),
        )

        for first, second in cases:
            with self.subTest(second=second.end):
                self.assertEqual(
                    len(detect_double_support_candidates((first, second), tolerances)),
                    1,
                )

    def test_each_numeric_gate_rejects_just_outside_its_boundary(self):
        tolerances = GeometryTolerances()
        radians = math.radians(tolerances.parallel_angle_tolerance_deg + 0.1)
        half_axis = (5000 * math.cos(radians), 5000 * math.sin(radians))
        cases = (
            dxf_strut("S2", (0, 1150.1), (10000, 1150.1)),
            dxf_strut("S2", (1001, 1000), (11001, 1000)),
            dxf_strut("S2", (0, 1000), (9749, 1000)),
            dxf_strut(
                "S2",
                (5000 - half_axis[0], 1000 - half_axis[1]),
                (5000 + half_axis[0], 1000 + half_axis[1]),
            ),
        )
        first = dxf_strut("S1", (0, 0), (10000, 0))

        for second in cases:
            with self.subTest(second=second.end):
                self.assertEqual(
                    detect_double_support_candidates((first, second), tolerances),
                    (),
                )

    def test_full_graph_marks_eligible_and_pending_edges_ambiguous(self):
        center = self._with_terminal_topology(
            dxf_strut("S1", (0, 0), (10000, 0))
        )
        eligible = self._with_terminal_topology(
            dxf_strut("S2", (0, 1000), (10000, 1000))
        )
        pending = self._with_terminal_topology(
            dxf_strut("S3", (0, -1000), (10000, -1000)),
            start_issue=(("WA",), ("WC",)),
        )

        candidates = detect_double_support_candidates((eligible, pending, center))

        self.assertEqual(
            {candidate.qualification_status for candidate in candidates},
            {"eligible", "pending_waler"},
        )
        self.assertTrue(all(candidate.ambiguous for candidate in candidates))
        self.assertFalse(any(candidate.accepted for candidate in candidates))
        self.assertEqual(
            [
                (
                    frozenset((item.first_strut_id, item.second_strut_id)),
                    item.qualification_status,
                    item.ambiguous,
                    item.accepted,
                )
                for item in candidates
            ],
            [
                (
                    frozenset((item.first_strut_id, item.second_strut_id)),
                    item.qualification_status,
                    item.ambiguous,
                    item.accepted,
                )
                for item in detect_double_support_candidates(
                    tuple(reversed((eligible, pending, center)))
                )
            ],
        )

    def test_incompatible_edge_also_blocks_eligible_default_acceptance(self):
        center = self._with_terminal_topology(
            dxf_strut("S1", (0, 0), (10000, 0))
        )
        eligible = self._with_terminal_topology(
            dxf_strut("S2", (0, 1000), (10000, 1000))
        )
        incompatible = self._with_terminal_topology(
            dxf_strut("S3", (0, -1000), (10000, -1000)),
            start=("WX",),
            end=("WY",),
        )

        candidates = detect_double_support_candidates(
            (center, eligible, incompatible)
        )

        self.assertEqual(
            {candidate.qualification_status for candidate in candidates},
            {"eligible", "incompatible_waler"},
        )
        self.assertTrue(all(candidate.ambiguous for candidate in candidates))
        self.assertFalse(any(candidate.accepted for candidate in candidates))

    def test_disappearing_conflict_edge_restores_unique_eligible_default(self):
        center = self._with_terminal_topology(
            dxf_strut("S1", (0, 0), (10000, 0))
        )
        eligible = self._with_terminal_topology(
            dxf_strut("S2", (0, 1000), (10000, 1000))
        )
        pending = self._with_terminal_topology(
            dxf_strut("S3", (0, -1000), (10000, -1000)),
            start_issue=(("WA",), ("WC",)),
        )
        conflicted = detect_double_support_candidates(
            (center, eligible, pending)
        )
        moved = replace(
            pending,
            start=(0, -2000),
            end=(10000, -2000),
            world_start=(0, -2000),
            world_end=(10000, -2000),
        )

        rebuilt = detect_double_support_candidates((center, eligible, moved))

        self.assertFalse(any(candidate.accepted for candidate in conflicted))
        self.assertEqual(len(rebuilt), 1)
        self.assertFalse(rebuilt[0].ambiguous)
        self.assertTrue(rebuilt[0].accepted)

    def test_canonical_rebuild_remeasures_pending_pair_before_upgrade(self):
        first = self._with_terminal_topology(
            dxf_strut("S1", (0, 0), (10000, 0))
        )
        pending_second = self._with_terminal_topology(
            dxf_strut("S2", (0, 1000), (10000, 1000)),
            start_issue=(("WA",), ("WC",)),
        )
        pending = detect_double_support_candidates((first, pending_second))[0]
        resolved_second = self._with_terminal_topology(
            replace(
                pending_second,
                start=(0, 1100),
                end=(10000, 1100),
                world_start=(0, 1100),
                world_end=(10000, 1100),
            )
        )

        rebuilt = detect_double_support_candidates((first, resolved_second))[0]

        self.assertEqual(pending.qualification_status, "pending_waler")
        self.assertAlmostEqual(pending.centerline_spacing, 1000)
        self.assertEqual(rebuilt.qualification_status, "eligible")
        self.assertAlmostEqual(rebuilt.centerline_spacing, 1100)
        self.assertTrue(rebuilt.accepted)

    def test_noneligible_candidate_cannot_be_accepted_or_create_formal_effects(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        pending = replace(
            detect_double_support_candidates(struts)[0],
            qualification_status="pending_waler",
            accepted=True,
        )
        self.assertFalse(pending.accepted)
        self.assertEqual(
            set_double_support_candidate_accepted((pending,), pending.id, True),
            (pending,),
        )
        object.__setattr__(pending, "accepted", True)
        result = dxf_result(struts, (), (pending,))
        self.assertEqual(result.summary()["double_support_groups"], 0)
        self.assertTrue(
            all(not row["SharedLayoutGroup"] for row in result.to_project_rows()["struts"])
        )
        associated, _columns, _beams, records, _messages = (
            associate_components_to_struts(
                struts,
                (dxf_column("C1", (3000, 498.5)),),
                (),
                double_support_candidates=(pending,),
            )
        )
        self.assertEqual(
            [strut.associated_columns for strut in associated],
            [("C1",), ()],
        )
        self.assertEqual([record.strut_id for record in records], ["S1"])

    def test_spacing_outside_tolerance_is_not_a_candidate(self):
        candidates = detect_double_support_candidates((
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1200), (10000, 1200)),
        ))

        self.assertEqual(candidates, ())

    def test_three_struts_produce_unaccepted_ambiguous_candidates(self):
        candidates = detect_double_support_candidates((
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
            dxf_strut("S3", (0, 2000), (10000, 2000)),
        ))

        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.ambiguous for candidate in candidates))
        self.assertFalse(any(candidate.accepted for candidate in candidates))

        updated = set_double_support_candidate_accepted(
            candidates,
            candidates[0].id,
            True,
        )
        self.assertTrue(updated[0].accepted)
        self.assertFalse(updated[1].accepted)

    def test_accepted_pair_receives_shared_column_with_independent_stations(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (5, 1000), (10005, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        candidates = detect_double_support_candidates(struts)

        associated, columns, _beams, records, messages = (
            associate_components_to_struts(
                struts,
                (column,),
                (),
                double_support_candidates=candidates,
            )
        )

        by_id = {strut.id: strut for strut in associated}
        self.assertEqual(columns[0].associated_strut_id, "S1")
        self.assertEqual(by_id["S1"].associated_columns, ("C1",))
        self.assertEqual(by_id["S2"].associated_columns, ("C1",))
        self.assertAlmostEqual(by_id["S1"].column_positions[0], 3000.0)
        self.assertAlmostEqual(by_id["S2"].column_positions[0], 2995.0)
        column_records = [
            record for record in records if record.component_role == "column"
        ]
        self.assertEqual(
            {record.strut_id for record in column_records},
            {"S1", "S2"},
        )
        self.assertEqual(
            {record.strut_id: record.station for record in column_records},
            {"S1": 3000.0, "S2": 2995.0},
        )
        self.assertFalse(
            any(
                message.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
                for message in messages
            )
        )
        result = replace(
            dxf_result(associated, columns, candidates),
            component_associations=records,
            messages=messages,
        )
        rows_by_id = {
            row["StrutID"]: row
            for row in result.to_project_rows()["struts"]
        }
        self.assertEqual(rows_by_id["S1"]["AssociatedColumnIDs"], "C1")
        self.assertEqual(rows_by_id["S2"]["AssociatedColumnIDs"], "C1")
        self.assertEqual(rows_by_id["S1"]["ColumnPositions"], "3000")
        self.assertEqual(rows_by_id["S2"]["ColumnPositions"], "2995")

    def test_rejected_pair_and_ordinary_neighbours_remain_primary_only(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        detected = detect_double_support_candidates(struts)
        rejected = (replace(detected[0], accepted=False),)

        rejected_struts, rejected_columns, _beams, rejected_records, _messages = (
            associate_components_to_struts(
                struts,
                (column,),
                (),
                double_support_candidates=rejected,
            )
        )
        ordinary_struts, ordinary_columns, _beams, ordinary_records, _messages = (
            associate_components_to_struts(struts, (column,), ())
        )

        for associated, columns, records in (
            (rejected_struts, rejected_columns, rejected_records),
            (ordinary_struts, ordinary_columns, ordinary_records),
        ):
            by_id = {strut.id: strut for strut in associated}
            self.assertEqual(columns[0].associated_strut_id, "S1")
            self.assertEqual(by_id["S1"].associated_columns, ("C1",))
            self.assertEqual(by_id["S2"].associated_columns, ())
            self.assertEqual(
                [record.strut_id for record in records],
                ["S1"],
            )

    def test_conflicting_accepted_group_membership_stays_primary_only(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
            dxf_strut("S3", (0, -1000), (10000, -1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        detected = detect_double_support_candidates(struts)
        conflicting = tuple(
            replace(candidate, accepted=True) for candidate in detected
        )

        associated, _columns, _beams, records, messages = (
            associate_components_to_struts(
                struts,
                (column,),
                (),
                double_support_candidates=conflicting,
            )
        )

        by_id = {strut.id: strut for strut in associated}
        self.assertEqual(by_id["S1"].associated_columns, ("C1",))
        self.assertEqual(by_id["S2"].associated_columns, ())
        self.assertEqual(by_id["S3"].associated_columns, ())
        self.assertEqual([record.strut_id for record in records], ["S1"])
        self.assertTrue(
            any(
                message.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
                and "多個已採用雙路群組" in message.message
                for message in messages
            )
        )

    def test_rebuild_toggle_is_reversible_idempotent_and_clears_stale_values(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        detected = detect_double_support_candidates(struts)
        rejected = (replace(detected[0], accepted=False),)
        result = rebuild_component_associations(
            dxf_result(struts, (column,), rejected)
        )
        self.assertEqual(
            [strut.associated_columns for strut in result.struts],
            [("C1",), ()],
        )

        accepted = set_double_support_candidate_accepted(
            result.double_support_candidates,
            result.double_support_candidates[0].id,
            True,
        )
        result = rebuild_component_associations(
            replace(result, double_support_candidates=accepted)
        )
        result = rebuild_component_associations(result)
        self.assertEqual(
            [strut.associated_columns for strut in result.struts],
            [("C1",), ("C1",)],
        )
        self.assertEqual(
            len(
                [
                    record
                    for record in result.component_associations
                    if record.component_role == "column"
                ]
            ),
            2,
        )

        rejected_again = set_double_support_candidate_accepted(
            result.double_support_candidates,
            result.double_support_candidates[0].id,
            False,
        )
        result = rebuild_component_associations(
            replace(result, double_support_candidates=rejected_again)
        )
        self.assertEqual(
            [strut.associated_columns for strut in result.struts],
            [("C1",), ()],
        )
        self.assertEqual(result.struts[1].column_positions, ())

    def test_reverse_pair_keeps_local_stations_then_project_rows_align_them(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut(
                "S2",
                (10005, 1000),
                (5, 1000),
                from_waler="W2",
                to_waler="W1",
            ),
        )
        column = dxf_column("C1", (3000, 498.5))
        candidates = detect_double_support_candidates(struts)
        associated, columns, beams, records, messages = (
            associate_components_to_struts(
                struts,
                (column,),
                (),
                double_support_candidates=candidates,
            )
        )
        result = replace(
            dxf_result(associated, columns, candidates),
            component_associations=records,
            messages=messages,
            beams=beams,
        )

        self.assertAlmostEqual(associated[0].column_positions[0], 3000.0)
        self.assertAlmostEqual(associated[1].column_positions[0], 7005.0)
        rows = result.to_project_rows()["struts"]
        self.assertEqual(rows[0]["ColumnPositions"], "3000")
        self.assertEqual(rows[1]["ColumnPositions"], "2995")

    def test_geometry_rebuild_does_not_retain_partner_column_when_out_of_range(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        candidates = detect_double_support_candidates(struts)
        result = rebuild_component_associations(
            dxf_result(struts, (column,), candidates)
        )
        moved_partner = replace(
            result.struts[1],
            start=(0, 2000),
            end=(10000, 2000),
            world_start=(0, 2000),
            world_end=(10000, 2000),
        )

        rebuilt = rebuild_component_associations(
            replace(result, struts=(result.struts[0], moved_partner))
        )

        self.assertEqual(rebuilt.struts[0].associated_columns, ("C1",))
        self.assertEqual(rebuilt.struts[1].associated_columns, ())
        self.assertEqual(rebuilt.struts[1].column_positions, ())


    def test_staged_rerecognition_preserves_rejected_pair_and_rebuilds(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        detected = detect_double_support_candidates(struts)
        current = rebuild_component_associations(
            dxf_result(
                struts,
                (column,),
                (replace(detected[0], accepted=False),),
            )
        )
        staged_auto = rebuild_component_associations(
            dxf_result(struts, (column,), detected)
        )
        importer = SimpleNamespace(
            tolerances=GeometryTolerances(),
            convert=lambda **_options: staged_auto,
            source_fingerprint=current.source_fingerprint,
            layer_names=current.layer_names,
        )
        workflow = DXFReviewWorkflow(
            importer,
            "double-support.dxf",
            initial_world_result=current,
        )

        staged, report = workflow.recognize_staged(
            (),
            layer_roles={"STRUT": "strut"},
        )

        self.assertFalse(staged.double_support_candidates[0].accepted)
        self.assertEqual(
            [strut.associated_columns for strut in staged.struts],
            [("C1",), ()],
        )
        self.assertEqual(report.preserved, ())

    def test_rerecognition_matches_pair_decisions_by_source_not_renumbered_id(self):
        previous_struts = (
            replace(
                dxf_strut("S1", (0, 0), (10000, 0)),
                source_handles=("HANDLE-A",),
            ),
            replace(
                dxf_strut("S2", (0, 1000), (10000, 1000)),
                source_handles=("HANDLE-B",),
            ),
        )
        previous_candidates = tuple(
            replace(candidate, accepted=False)
            for candidate in detect_double_support_candidates(previous_struts)
        )
        previous = dxf_result(previous_struts, (), previous_candidates)
        renumbered_struts = (
            replace(previous_struts[0], id="S8"),
            replace(previous_struts[1], id="S9"),
        )
        renumbered = dxf_result(
            renumbered_struts,
            (),
            detect_double_support_candidates(renumbered_struts),
        )
        reused_ids_with_other_sources = (
            replace(previous_struts[0], source_handles=("HANDLE-X",)),
            replace(previous_struts[1], source_handles=("HANDLE-Y",)),
        )
        unrelated = dxf_result(
            reused_ids_with_other_sources,
            (),
            detect_double_support_candidates(reused_ids_with_other_sources),
        )

        preserved = preserve_double_support_result_decisions(
            previous,
            renumbered,
        )
        not_misapplied = preserve_double_support_result_decisions(
            previous,
            unrelated,
        )

        self.assertFalse(preserved[0].accepted)
        self.assertTrue(not_misapplied[0].accepted)

    def test_accepted_candidate_is_written_as_one_project_group(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        result = DXFImportResult(
            source_path="drawing.dxf",
            layer_names=("STRUT",),
            selected_layers={"strut": ("STRUT",)},
            layer_info=(),
            walers=(),
            struts=struts,
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={"strut": 2},
            double_support_candidates=detect_double_support_candidates(
                struts,
                GeometryTolerances(),
            ),
        )

        rows = result.to_project_rows()["struts"]

        self.assertEqual(rows[0]["SharedLayoutGroup"], "G1")
        self.assertEqual(rows[1]["SharedLayoutGroup"], "G1")

    def test_reversed_dxf_member_is_aligned_before_creating_project_rows(self):
        second = replace(
            dxf_strut(
                "S2",
                (10000, 1000),
                (0, 1000),
                from_waler="W2",
                to_waler="W1",
            ),
            beam_positions=(2500,),
            column_positions=(7000,),
            from_brace_to_waler_start_len=100,
            from_brace_to_waler_end_len=200,
            to_brace_to_waler_start_len=300,
            to_brace_to_waler_end_len=400,
        )
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            second,
        )
        result = DXFImportResult(
            source_path="drawing.dxf",
            layer_names=("STRUT",),
            selected_layers={"strut": ("STRUT",)},
            layer_info=(),
            walers=(),
            struts=struts,
            braces=(),
            entity_debug=(),
            messages=(),
            source_entity_counts={"strut": 2},
            double_support_candidates=detect_double_support_candidates(struts),
        )

        rows = result.to_project_rows()["struts"]

        self.assertEqual(
            [(row["FromWaler"], row["ToWaler"]) for row in rows],
            [("W1", "W2"), ("W1", "W2")],
        )
        self.assertEqual(
            [(row["StartX"], row["EndX"]) for row in rows],
            [(0, 10000), (0, 10000)],
        )
        self.assertEqual(rows[1]["BeamPositions"], "7500")
        self.assertEqual(rows[1]["ColumnPositions"], "3000")
        self.assertEqual(rows[1]["FromBraceToWalerStartLen"], 300)
        self.assertEqual(rows[1]["FromBraceToWalerEndLen"], 400)
        self.assertEqual(rows[1]["ToBraceToWalerStartLen"], 100)
        self.assertEqual(rows[1]["ToBraceToWalerEndLen"], 200)

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_ambiguous_column_baseline(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        result = importer.convert(layer_roles=layer_roles)
        column = next(item for item in result.columns if item.id == "C25")
        by_id = {item.id: item for item in result.struts}
        center = column.world_reference_point
        self.assertIsNotNone(center)

        def distance_to_axis(strut):
            start = strut.world_start or strut.start
            end = strut.world_end or strut.end
            axis = (end[0] - start[0], end[1] - start[1])
            length = math.hypot(*axis)
            station = ((center[0] - start[0]) * axis[0] + (center[1] - start[1]) * axis[1]) / length
            self.assertGreaterEqual(station, 0)
            self.assertLessEqual(station, length)
            return math.hypot(
                center[0] - start[0] - axis[0] * station / length,
                center[1] - start[1] - axis[1] * station / length,
            )

        self.assertAlmostEqual(distance_to_axis(by_id["S20"]), 498.5, delta=1)
        self.assertAlmostEqual(distance_to_axis(by_id["S35"]), 501.5, delta=1)
        self.assertEqual(column.associated_strut_id, "S20")
        self.assertEqual(
            [item.strut_id for item in result.component_associations if item.component_id == "C25"],
            ["S20"],
        )
        self.assertTrue(any(
            message.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
            and "C25" in message.message
            for message in result.messages
        ))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_manual_single_overrides_nearest_and_restores(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        column = next(item for item in original.columns if item.id == "C25")
        by_id = {item.id: item for item in original.struts}
        decision = ColumnAssociationDecision(
            column.source_handles,
            (by_id["S20"].source_handles, by_id["S35"].source_handles),
            (by_id["S35"].source_handles,),
            original.source_fingerprint,
            "C25",
        )
        manual = rebuild_component_associations(
            original, importer.tolerances, column_decisions=(decision,)
        )
        self.assertEqual(
            [item.strut_id for item in manual.component_associations if item.component_id == "C25"],
            ["S35"],
        )
        self.assertNotIn("C25", next(item for item in manual.struts if item.id == "S20").associated_columns)
        self.assertIn("C25", next(item for item in manual.struts if item.id == "S35").associated_columns)
        self.assertFalse(any(
            item.code == "AMBIGUOUS_COMPONENT_ASSOCIATION" and "C25" in item.message
            for item in manual.messages
        ))
        self.assertTrue(any(item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED" for item in manual.messages))
        self.assertEqual(
            manual,
            rebuild_component_associations(manual, importer.tolerances, column_decisions=(decision,)),
        )
        withdrawn = rebuild_component_associations(manual, importer.tolerances)
        self.assertEqual(
            [item.strut_id for item in withdrawn.component_associations if item.component_id == "C25"],
            ["S20"],
        )
        self.assertTrue(any(
            item.code == "AMBIGUOUS_COMPONENT_ASSOCIATION" and "C25" in item.message
            for item in withdrawn.messages
        ))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_manual_double_has_independent_stations_without_shared_layout(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        column = next(item for item in original.columns if item.id == "C25")
        by_id = {item.id: item for item in original.struts}
        decision = ColumnAssociationDecision(
            column.source_handles,
            (by_id["S20"].source_handles, by_id["S35"].source_handles),
            (by_id["S20"].source_handles, by_id["S35"].source_handles),
            original.source_fingerprint,
            "C25",
        )
        manual = rebuild_component_associations(
            original, importer.tolerances, column_decisions=(decision,)
        )
        associations = [item for item in manual.component_associations if item.component_id == "C25"]
        self.assertEqual({item.strut_id for item in associations}, {"S20", "S35"})
        options = column_association_options(column, original.struts, importer.tolerances)
        self.assertEqual(
            {item.strut_id: item.station for item in associations},
            {option[1]: option[2] for option in options[:2]},
        )
        importable_projection = replace(
            manual,
            messages=tuple(item for item in manual.messages if item.severity not in {"error", "critical"}),
        )
        rows = {row["StrutID"]: row for row in importable_projection.to_project_rows()["struts"]}
        for strut_id in ("S20", "S35"):
            self.assertIn("C25", rows[strut_id]["AssociatedColumnIDs"])
            self.assertFalse(rows[strut_id]["SharedLayoutGroup"])

    def test_manual_two_strut_column_decision_does_not_accept_pending_waler_pair(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (10000, 1000), (0, 1000)),
        )
        column = dxf_column("C1", (3000, 500))
        pending = replace(
            detect_double_support_candidates(struts)[0],
            qualification_status="pending_waler", accepted=False,
        )
        original = dxf_result(struts, (column,), (pending,))
        decision = ColumnAssociationDecision(
            column.source_handles,
            (struts[0].source_handles, struts[1].source_handles),
            (struts[0].source_handles, struts[1].source_handles),
            original.source_fingerprint,
            column.id,
        )
        manual = rebuild_component_associations(original, column_decisions=(decision,))
        self.assertEqual(
            [(item.strut_id, item.station) for item in manual.component_associations],
            [("S1", 3000), ("S2", 7000)],
        )
        self.assertEqual(manual.double_support_candidates, (pending,))
        self.assertFalse(any(row["SharedLayoutGroup"] for row in manual.to_project_rows()["struts"]))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_invalid_manual_decision_requires_review_without_stale_station(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        column = next(item for item in original.columns if item.id == "C25")
        by_id = {item.id: item for item in original.struts}
        decision = ColumnAssociationDecision(
            column.source_handles,
            (by_id["S20"].source_handles, by_id["S35"].source_handles),
            (by_id["S35"].source_handles,),
            "STALE-FINGERPRINT",
            "C25",
        )
        rebuilt = rebuild_component_associations(
            original, importer.tolerances, column_decisions=(decision,)
        )
        self.assertEqual(
            [item.strut_id for item in rebuilt.component_associations if item.component_id == "C25"],
            ["S20"],
        )
        self.assertTrue(any(item.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW" for item in rebuilt.messages))
        self.assertFalse(any(item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED" for item in rebuilt.messages))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_workflow_commit_and_withdraw_warning_lifecycle(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        workflow = DXFReviewWorkflow(importer, PROJECT_ROOT / "Y29_test.dxf", initial_world_result=original)
        baseline = workflow.completion_status()
        plan = workflow.plan_column_association_repair("C25")
        self.assertEqual(plan.status, "unresolved")
        self.assertEqual(plan.candidate_strut_ids, ("S20", "S35"))
        self.assertEqual(workflow.revision, plan.base_revision)
        self.assertEqual(workflow.completion_status(), baseline)
        with self.assertRaisesRegex(Exception, "必須明確選擇"):
            workflow.commit_column_association_repair(plan, ())
        with self.assertRaisesRegex(Exception, "必須明確選擇"):
            workflow.commit_column_association_repair(plan, ("S99",))
        before_stage = workflow.world_result
        with patch("dxf_import.review_workflow.build_problem_records", side_effect=RuntimeError("stage failed")):
            with self.assertRaisesRegex(RuntimeError, "stage failed"):
                workflow.commit_column_association_repair(plan, ("S35",))
        self.assertIs(workflow.world_result, before_stage)
        self.assertEqual(workflow.revision, plan.base_revision)
        self.assertEqual(workflow.column_association_decisions, {})

        workflow.commit_column_association_repair(plan, ("S35",))
        self.assertEqual(workflow.plan_column_association_repair("C25").status, "repaired")
        self.assertEqual(workflow.completion_status().warning_count, baseline.warning_count - 1)
        self.assertEqual(workflow.completion_status().blocking_error_count, baseline.blocking_error_count)
        self.assertTrue(any(
            item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED" and "C25" in item.message
            for item in workflow.world_result.messages
        ))
        with self.assertRaisesRegex(Exception, "重新預覽"):
            workflow.commit_column_association_repair(plan, ("S20",))
        self.assertEqual(workflow.plan_column_association_repair("C25").selected_strut_ids, ("S35",))

        workflow.withdraw_column_association_repair(workflow.plan_column_association_repair("C25"))
        self.assertEqual(workflow.plan_column_association_repair("C25").status, "unresolved")
        self.assertEqual(workflow.completion_status().warning_count, baseline.warning_count)
        self.assertEqual(
            [item.strut_id for item in workflow.world_result.component_associations if item.component_id == "C25"],
            ["S20"],
        )

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_saved_decision_replays_and_invalid_geometry_requires_review(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        workflow = DXFReviewWorkflow(importer, PROJECT_ROOT / "Y29_test.dxf", initial_world_result=original)
        workflow.commit_column_association_repair(
            workflow.plan_column_association_repair("C25"), ("S35",)
        )
        state = workflow.serialize_review_state(layer_roles=layer_roles)
        self.assertEqual(state["review_state_version"], 2)
        self.assertEqual(len(state["column_association_decisions"]), 1)

        resumed = DXFReviewWorkflow(
            importer, PROJECT_ROOT / "Y29_test.dxf",
            initial_state=state, resume_review=True, initial_world_result=original,
        )
        self.assertEqual(resumed.plan_column_association_repair("C25").status, "repaired")
        self.assertEqual(
            [item.strut_id for item in resumed.world_result.component_associations if item.component_id == "C25"],
            ["S35"],
        )

        reversed_struts = tuple(
            replace(strut, start=strut.end, end=strut.start,
                    world_start=strut.world_end or strut.end,
                    world_end=strut.world_start or strut.start)
            if strut.id == "S35" else strut
            for strut in original.struts
        )
        reversed_result = replace(original, struts=reversed_struts)
        reversed_workflow = DXFReviewWorkflow(
            importer, PROJECT_ROOT / "Y29_test.dxf",
            initial_state=state, resume_review=True, initial_world_result=reversed_result,
        )
        old_station = next(
            item.station for item in resumed.world_result.component_associations
            if item.component_id == "C25" and item.strut_id == "S35"
        )
        new_station = next(
            item.station for item in reversed_workflow.world_result.component_associations
            if item.component_id == "C25" and item.strut_id == "S35"
        )
        reversed_strut = next(item for item in reversed_workflow.world_result.struts if item.id == "S35")
        self.assertAlmostEqual(
            new_station + old_station,
            math.dist(reversed_strut.world_start or reversed_strut.start,
                      reversed_strut.world_end or reversed_strut.end),
        )

        displaced_struts = tuple(
            replace(strut, start=(strut.start[0] + 50000, strut.start[1] + 50000),
                    end=(strut.end[0] + 50000, strut.end[1] + 50000),
                    world_start=(strut.start[0] + 50000, strut.start[1] + 50000),
                    world_end=(strut.end[0] + 50000, strut.end[1] + 50000))
            if strut.id == "S35" else strut
            for strut in original.struts
        )
        invalid = DXFReviewWorkflow(
            importer, PROJECT_ROOT / "Y29_test.dxf",
            initial_state=state, resume_review=True,
            initial_world_result=replace(original, struts=displaced_struts),
        )
        self.assertEqual(invalid.plan_column_association_repair("C25").status, "requires_review")
        self.assertFalse(any(
            item.component_id == "C25" and item.strut_id == "S35"
            for item in invalid.world_result.component_associations
        ))
        self.assertTrue(any(item.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW" for item in invalid.world_result.messages))
        self.assertFalse(any(item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED" for item in invalid.world_result.messages))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_source_exclusion_disables_and_restore_revalidates_decision(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        workflow = DXFReviewWorkflow(importer, PROJECT_ROOT / "Y29_test.dxf", initial_world_result=original)
        workflow.commit_column_association_repair(
            workflow.plan_column_association_repair("C25"), ("S35",)
        )
        removed = next(item for item in workflow.world_result.struts if item.id == "S35")
        exclusion_plan = workflow.plan_source_exclusion_change(
            (ExcludedSource("strut", removed.source_handles),)
        )
        self.assertFalse(any(
            item.component_id == "C25" and item.strut_id == "S35"
            for item in exclusion_plan.world_result.component_associations
        ))
        self.assertTrue(any(
            item.code == "COLUMN_ASSOCIATION_REQUIRES_REVIEW"
            for item in exclusion_plan.world_result.messages
        ))
        workflow.commit_source_exclusion_plan(exclusion_plan)
        restore_plan = workflow.plan_source_exclusion_change(())
        self.assertTrue(any(
            item.code == "COLUMN_ASSOCIATION_MANUALLY_RESOLVED"
            for item in restore_plan.world_result.messages
        ))

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_c25_manual_decision_survives_unrelated_double_support_change(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[Y29_LAYER_MAPPING.get(layer, "忽略")]
            for layer in importer.layer_names
        }
        original = importer.convert(layer_roles=layer_roles)
        workflow = DXFReviewWorkflow(importer, PROJECT_ROOT / "Y29_test.dxf", initial_world_result=original)
        workflow.commit_column_association_repair(
            workflow.plan_column_association_repair("C25"), ("S35",)
        )
        candidate = next((item for item in workflow.world_result.double_support_candidates
                          if item.qualification_status == "eligible"
                          and item.accepted
                          and "S20" not in (item.first_strut_id, item.second_strut_id)
                          and "S35" not in (item.first_strut_id, item.second_strut_id)), None)
        if candidate is None:
            self.skipTest("No unrelated accepted pair in Y29 fixture")
        updated = tuple(
            replace(item, accepted=False) if item.id == candidate.id else item
            for item in workflow.world_result.double_support_candidates
        )
        workflow.commit_double_support_candidates(updated)
        self.assertEqual(
            [item.strut_id for item in workflow.world_result.component_associations if item.component_id == "C25"],
            ["S35"],
        )
        self.assertEqual(workflow.plan_column_association_repair("C25").status, "repaired")

    @unittest.skipUnless(
        (PROJECT_ROOT / "Y29_test.dxf").exists(),
        "Y29_test.dxf regression fixture is not available",
    )
    def test_y29_unambiguous_shared_columns_constrain_both_accepted_lanes(self):
        importer = DXFImporter(PROJECT_ROOT / "Y29_test.dxf").read()
        layer_roles = {
            layer: DXFImportDialog.USE_TO_ROLE[
                Y29_LAYER_MAPPING.get(layer, "忽略")
            ]
            for layer in importer.layer_names
        }

        result = importer.convert(layer_roles=layer_roles)

        self.assertEqual(len(result.struts), 40)
        self.assertEqual(len(result.columns), 68)
        accepted = tuple(
            candidate
            for candidate in result.double_support_candidates
            if candidate.accepted
        )
        self.assertEqual(len(accepted), 10)
        accepted_pairs = {
            frozenset((candidate.first_strut_id, candidate.second_strut_id))
            for candidate in accepted
        }
        self.assertTrue(
            {
                frozenset(("S1", "S2")),
                frozenset(("S5", "S11")),
                frozenset(("S6", "S12")),
                frozenset(("S7", "S13")),
                frozenset(("S19", "S36")),
                frozenset(("S21", "S34")),
                frozenset(("S27", "S28")),
                frozenset(("S37", "S38")),
            }.isdisjoint(accepted_pairs)
        )
        self.assertTrue(
            any(
                message.code == "AMBIGUOUS_WALER_CONNECTION"
                and message.severity == "error"
                and message.role == "strut"
                for message in result.messages
            )
        )
        strut_by_id = {strut.id: strut for strut in result.struts}
        s19_s36 = next(
            candidate
            for candidate in result.double_support_candidates
            if {candidate.first_strut_id, candidate.second_strut_id}
            == {"S19", "S36"}
        )
        tolerances = GeometryTolerances()
        self.assertEqual(s19_s36.qualification_status, "pending_waler")
        self.assertFalse(s19_s36.accepted)
        self.assertLessEqual(
            abs(
                s19_s36.centerline_spacing
                - tolerances.double_support_spacing_mm
            ),
            tolerances.double_support_spacing_tolerance_mm,
        )
        self.assertLessEqual(
            s19_s36.angle_difference_deg,
            tolerances.parallel_angle_tolerance_deg,
        )
        self.assertGreaterEqual(
            s19_s36.overlap_ratio,
            tolerances.double_support_overlap_ratio,
        )
        self.assertLessEqual(
            s19_s36.length_difference,
            tolerances.double_support_length_tolerance_mm,
        )
        self.assertEqual(
            {(issue.member_id, issue.terminal_name) for issue in s19_s36.issues},
            {
                ("S19", "start"),
                ("S19", "end"),
                ("S36", "start"),
                ("S36", "end"),
            },
        )
        self.assertTrue(
            all(issue.competing_waler_source_handles for issue in s19_s36.issues)
        )
        associations_by_column = {}
        for association in result.component_associations:
            if association.component_role == "column":
                associations_by_column.setdefault(
                    association.component_id,
                    {},
                )[association.strut_id] = association
        shared = []
        for column in result.columns:
            associations = associations_by_column.get(column.id, {})
            matches = [
                candidate
                for candidate in accepted
                if {
                    candidate.first_strut_id,
                    candidate.second_strut_id,
                }.issubset(associations)
            ]
            if matches:
                self.assertEqual(len(matches), 1)
                shared.append((column, matches[0], associations))
        self.assertEqual(len(shared), 33)
        self.assertEqual(
            {column.id for column in result.columns if not column.associated_strut_id},
            {"C34", "C41"},
        )
        c26 = next(column for column in result.columns if column.id == "C26")
        self.assertEqual(c26.associated_strut_id, "S19")
        self.assertEqual(set(associations_by_column["C26"]), {"S19"})

        c7 = next(column for column in result.columns if column.id == "C7")
        self.assertEqual(c7.associated_strut_id, "S15")
        c7_associations = associations_by_column["C7"]
        self.assertEqual({"S15", "S17"}, set(c7_associations))
        for strut_id in ("S15", "S17"):
            strut = strut_by_id[strut_id]
            self.assertIn("C7", strut.associated_columns)
            start = strut.world_start or strut.start
            end = strut.world_end or strut.end
            reference = c7.world_reference_point or c7.reference_point
            length = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
            expected_station = (
                (reference[0] - start[0]) * (end[0] - start[0])
                + (reference[1] - start[1]) * (end[1] - start[1])
            ) / length
            self.assertAlmostEqual(
                c7_associations[strut_id].station,
                expected_station,
                places=6,
            )

        for _column, candidate, associations in shared:
            first = strut_by_id[candidate.first_strut_id]
            second = strut_by_id[candidate.second_strut_id]
            first_station = associations[first.id].station
            second_station = associations[second.id].station
            if (first.from_waler, first.to_waler) == (
                second.to_waler,
                second.from_waler,
            ):
                second_start = second.world_start or second.start
                second_end = second.world_end or second.end
                second_length = (
                    (second_end[0] - second_start[0]) ** 2
                    + (second_end[1] - second_start[1]) ** 2
                ) ** 0.5
                second_station = second_length - second_station
            self.assertAlmostEqual(first_station, second_station, delta=1.0)



class DoubleSupportReviewPersistenceTests(unittest.TestCase):
    def test_pending_state_is_not_persisted_as_rejection_and_upgrade_uses_default(self):
        struts = (
            replace(
                dxf_strut("S1", (0, 0), (10000, 0)),
                source_handles=("HANDLE-A",),
            ),
            replace(
                dxf_strut("S2", (0, 1000), (10000, 1000)),
                source_handles=("HANDLE-B",),
            ),
        )
        eligible = dxf_result(
            struts,
            (),
            detect_double_support_candidates(struts),
        )
        pending = replace(
            eligible,
            double_support_candidates=(
                replace(
                    eligible.double_support_candidates[0],
                    qualification_status="pending_waler",
                    accepted=False,
                ),
            ),
        )

        upgraded = preserve_double_support_result_decisions(pending, eligible)

        self.assertTrue(upgraded[0].accepted)

    def test_saved_decision_only_applies_while_current_pair_is_eligible(self):
        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        eligible = dxf_result(
            struts,
            (),
            detect_double_support_candidates(struts),
        )
        identity = double_support_candidate_identity(
            eligible,
            eligible.double_support_candidates[0],
        )
        pending = replace(
            eligible,
            double_support_candidates=(
                replace(
                    eligible.double_support_candidates[0],
                    qualification_status="pending_waler",
                    accepted=False,
                ),
            ),
        )

        still_pending = apply_double_support_decisions(pending, {identity: True})
        rejected_after_upgrade = apply_double_support_decisions(
            eligible,
            {identity: False},
        )

        self.assertFalse(still_pending[0].accepted)
        self.assertFalse(rejected_after_upgrade[0].accepted)

    def test_explicit_decision_survives_renumbering_by_source_identity(self):
        original_struts = (
            replace(
                dxf_strut("S1", (0, 0), (10000, 0)),
                source_handles=("HANDLE-A",),
            ),
            replace(
                dxf_strut("S2", (0, 1000), (10000, 1000)),
                source_handles=("HANDLE-B",),
            ),
        )
        original = dxf_result(
            original_struts,
            (),
            detect_double_support_candidates(original_struts),
        )
        identity = double_support_candidate_identity(
            original,
            original.double_support_candidates[0],
        )
        serialized = serialize_double_support_decisions({identity: False})

        renumbered_struts = (
            replace(original_struts[0], id="S21"),
            replace(original_struts[1], id="S22"),
        )
        rebuilt = dxf_result(
            renumbered_struts,
            (),
            detect_double_support_candidates(renumbered_struts),
        )
        decisions = double_support_decisions_from_review_state(
            {"double_support_decisions": serialized}
        )
        restored = apply_double_support_decisions(rebuilt, decisions)

        self.assertFalse(restored[0].accepted)
        self.assertEqual(
            serialized[0]["first_source_handles"],
            ["HANDLE-A"],
        )

    def test_decision_is_not_applied_to_reused_member_numbers(self):
        old_struts = (
            replace(dxf_strut("S1", (0, 0), (10000, 0)), source_handles=("A",)),
            replace(dxf_strut("S2", (0, 1000), (10000, 1000)), source_handles=("B",)),
        )
        old = dxf_result(
            old_struts,
            (),
            detect_double_support_candidates(old_struts),
        )
        identity = double_support_candidate_identity(
            old,
            old.double_support_candidates[0],
        )
        decisions = {identity: False}
        new_struts = (
            replace(old_struts[0], source_handles=("X",)),
            replace(old_struts[1], source_handles=("Y",)),
        )
        rebuilt = dxf_result(
            new_struts,
            (),
            detect_double_support_candidates(new_struts),
        )

        restored = apply_double_support_decisions(rebuilt, decisions)

        self.assertTrue(restored[0].accepted)


if __name__ == "__main__":
    unittest.main()
