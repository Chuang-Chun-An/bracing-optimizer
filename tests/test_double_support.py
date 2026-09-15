import unittest
import copy
from dataclasses import replace
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
    SupportInputBuilder,
    SupportZoneInput,
)
from bracing_optimizer.domain.material_rules import MaterialRatioTargets
from dxf_import.candidate_points import (
    associate_components_to_struts,
    rebuild_component_associations,
)
from dxf_import.dialog import DXFImportDialog
from dxf_import.importer import DXFImporter, Y29_LAYER_MAPPING
from dxf_import.models import (
    Column,
    DoubleSupportCandidate,
    DXFImportResult,
    GeometryTolerances,
    Strut,
)
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
        request = OptimizeSupportZoneRequest(
            input=SupportZoneInput("Z1", configs),
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
    def test_parallel_struts_at_1000_mm_become_one_candidate(self):
        candidates = detect_double_support_candidates((
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        ))

        self.assertEqual(len(candidates), 1)
        self.assertTrue(candidates[0].accepted)
        self.assertAlmostEqual(candidates[0].centerline_spacing, 1000)
        self.assertGreaterEqual(candidates[0].overlap_ratio, 0.9)

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

    def test_step7_toggle_rebuilds_associations_and_review_inputs(self):
        class DoubleSupportTree:
            def __init__(self, candidate_id):
                self.candidate_id = candidate_id
                self.selected = ""

            def selection(self):
                return (self.candidate_id,)

            def exists(self, candidate_id):
                return candidate_id == self.candidate_id

            def selection_set(self, candidate_id):
                self.selected = candidate_id

        struts = (
            dxf_strut("S1", (0, 0), (10000, 0)),
            dxf_strut("S2", (0, 1000), (10000, 1000)),
        )
        column = dxf_column("C1", (3000, 498.5))
        detected = detect_double_support_candidates(struts)
        result = rebuild_component_associations(
            dxf_result(
                struts,
                (column,),
                (replace(detected[0], accepted=False),),
            )
        )
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.result = result
        dialog.world_result = result
        dialog.importer = SimpleNamespace(tolerances=GeometryTolerances())
        dialog.double_support_tree = DoubleSupportTree(detected[0].id)
        refreshes = []

        def refresh(**options):
            dialog.problem_records = build_problem_records(dialog.result)
            dialog.review_items = build_review_items(
                dialog.result,
                dialog.problem_records,
            )
            refreshes.append(options)

        dialog._refresh_result_views = refresh

        dialog._toggle_selected_double_support()

        self.assertTrue(dialog.result.double_support_candidates[0].accepted)
        self.assertEqual(
            [strut.associated_columns for strut in dialog.result.struts],
            [("C1",), ("C1",)],
        )
        self.assertFalse(
            any(
                item.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
                for item in dialog.problem_records
            )
        )
        self.assertEqual(len(refreshes), 1)

        dialog._toggle_selected_double_support()

        self.assertFalse(dialog.result.double_support_candidates[0].accepted)
        self.assertEqual(
            [strut.associated_columns for strut in dialog.result.struts],
            [("C1",), ()],
        )
        self.assertTrue(
            any(
                item.code == "AMBIGUOUS_COMPONENT_ASSOCIATION"
                for item in dialog.problem_records
            )
        )
        self.assertEqual(len(refreshes), 2)
        self.assertEqual(dialog.double_support_tree.selected, detected[0].id)

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
        dialog = DXFImportDialog.__new__(DXFImportDialog)
        dialog.world_result = current
        dialog.material_specs = ()
        dialog.importer = SimpleNamespace(
            tolerances=GeometryTolerances(),
            convert=lambda **_options: staged_auto,
        )

        staged, report = dialog._recognize_staged_result(
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
    def test_y29_shared_columns_constrain_both_accepted_lanes(self):
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
        self.assertEqual(len(accepted), 18)
        strut_by_id = {strut.id: strut for strut in result.struts}
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
        self.assertEqual(len(shared), 58)
        self.assertEqual(
            {column.id for column in result.columns if not column.associated_strut_id},
            {"C34", "C41"},
        )

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
