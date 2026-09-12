import unittest
from dataclasses import replace
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
from dxf_import.models import DXFImportResult, GeometryTolerances, Strut
from dxf_import.support_pairing import (
    detect_double_support_candidates,
    set_double_support_candidate_accepted,
)


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
        source_width=0,
        from_waler=from_waler,
        to_waler=to_waler,
        confidence=1.0,
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


if __name__ == "__main__":
    unittest.main()
