import unittest
from dataclasses import replace

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_service import (
    ApplyDxfReviewRequest,
    ProjectService,
)
from bracing_optimizer.application.solver_input_builder import (
    SolverInputBuildError,
    SupportInputBuilder,
)
from bracing_optimizer.infrastructure.project_persistence import DxfWorkflowStatus
from dxf_import.initial_zoning import (
    INITIAL_ZONING_TOPOLOGY_AMBIGUOUS,
    INITIAL_ZONING_TOPOLOGY_CONFLICT,
    assign_initial_zoning,
)
from dxf_import.models import (
    DXFImportResult,
    DoubleSupportCandidate,
    Strut,
    Waler,
)


def waler(identifier, start, end):
    return Waler(
        id=identifier,
        start=start,
        end=end,
        source_layer="WALER",
        source_handles=(f"H-{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=350,
        confidence=1.0,
    )


def strut(identifier, y, *, start_x=0, end_x=10000, walers=("WL", "WR")):
    return Strut(
        id=identifier,
        start=(start_x, y),
        end=(end_x, y),
        source_layer="STRUT",
        source_handles=(f"H-{identifier}",),
        source_entity_types=("LINE",),
        recognition_method="existing_centerline",
        centerline_computed=False,
        source_width=350,
        from_waler=walers[0],
        to_waler=walers[1],
        confidence=1.0,
    )


def result(*, walers, struts, candidates=()):
    return DXFImportResult(
        source_path="reviewed.dxf",
        layer_names=("WALER", "STRUT"),
        selected_layers={"waler": ("WALER",), "strut": ("STRUT",)},
        layer_info=(),
        walers=tuple(walers),
        struts=tuple(struts),
        braces=(),
        entity_debug=(),
        messages=(),
        source_entity_counts={"waler": len(walers), "strut": len(struts)},
        double_support_candidates=tuple(candidates),
    )


def zoning_members(outcome):
    groups = {}
    for member, zoning in outcome.assignments:
        groups.setdefault(zoning, set()).add(member)
    return {frozenset(members) for members in groups.values()}


class InitialZoningTests(unittest.TestCase):
    def setUp(self):
        self.chain_walers = (
            waler("WL-A", (0, -1000), (0, 100)),
            waler("WL-B", (0, 100), (0, 2000)),
            waler("WR-A", (10000, -1000), (10000, 100)),
            waler("WR-B", (10000, 100), (10000, 2000)),
        )

    def test_different_waler_members_on_same_continuous_chains_share_row(self):
        source = result(
            walers=self.chain_walers,
            struts=(
                strut("S1", -500, walers=("WL-A", "WR-A")),
                strut("S2", 500, walers=("WL-B", "WR-B")),
            ),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual({frozenset(("S1", "S2"))}, zoning_members(outcome))

    def test_explicitly_different_chain_pairs_are_not_spatially_merged(self):
        walers = (*self.chain_walers, waler("XL", (20000, -1000), (20000, 2000)),
                  waler("XR", (30000, -1000), (30000, 2000)))
        source = result(
            walers=walers,
            struts=(
                strut("S1", 0, walers=("WL-A", "WR-A")),
                strut("S2", 100, start_x=20000, end_x=30000, walers=("XL", "XR")),
            ),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual({frozenset(("S1",)), frozenset(("S2",))}, zoning_members(outcome))

    def test_order_endpoint_reversal_and_large_gap_do_not_change_membership(self):
        first = strut("S1", 0, walers=("WL-A", "WR-A"))
        second = strut("S2", 100000, walers=("WL-B", "WR-B"))
        original = assign_initial_zoning(result(
            walers=self.chain_walers,
            struts=(first, second),
        ))
        reversed_source = result(
            walers=tuple(reversed(self.chain_walers)),
            struts=(replace(second, start=second.end, end=second.start,
                            world_start=second.end, world_end=second.start), first),
        )

        reordered = assign_initial_zoning(reversed_source)

        self.assertEqual(zoning_members(original), zoning_members(reordered))
        self.assertEqual({frozenset(("S1", "S2"))}, zoning_members(reordered))

    def test_out_of_tolerance_middle_support_is_a_boundary_and_cannot_be_skipped(self):
        source = result(
            walers=self.chain_walers,
            struts=(
                strut("S1", 0, walers=("WL-A", "WR-A")),
                strut("S2", 100, end_x=12000, walers=("WL-A", "WR-A")),
                strut("S3", 200, walers=("WL-B", "WR-B")),
            ),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual(
            {frozenset(("S1",)), frozenset(("S2",)), frozenset(("S3",))},
            zoning_members(outcome),
        )

    def test_missing_topology_uses_only_spatially_adjacent_fallback(self):
        source = result(
            walers=self.chain_walers,
            struts=(
                strut("S1", 0, walers=("WL-A", "WR-A")),
                strut("S2", 100, walers=("", "")),
                strut("S3", 200, walers=("WL-B", "WR-B")),
            ),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual({frozenset(("S1", "S2", "S3"))}, zoning_members(outcome))
        self.assertEqual((), outcome.diagnostics)

    def test_unknown_between_conflicting_topologies_is_conservatively_independent(self):
        walers = (*self.chain_walers, waler("XL", (20000, -1000), (20000, 2000)),
                  waler("XR", (30000, -1000), (30000, 2000)))
        source = result(
            walers=walers,
            struts=(
                strut("S1", 0, walers=("WL-A", "WR-A")),
                strut("UNKNOWN", 100, walers=("", "")),
                strut("S2", 200, walers=("XL", "XR")),
            ),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual(
            {frozenset(("S1",)), frozenset(("UNKNOWN",)), frozenset(("S2",))},
            zoning_members(outcome),
        )
        self.assertEqual(
            [INITIAL_ZONING_TOPOLOGY_AMBIGUOUS],
            [item.code for item in outcome.diagnostics],
        )

    def test_confirmed_double_support_is_one_ordering_unit_and_one_zoning(self):
        first = strut("S1-A", 100, walers=("WL-A", "WR-A"))
        second = strut("S1-B", 110, walers=("WL-A", "WR-A"))
        candidate = DoubleSupportCandidate(
            id="D1",
            first_strut_id=first.id,
            second_strut_id=second.id,
            centerline_spacing=10,
            angle_difference_deg=0,
            overlap_ratio=1,
            length_difference=0,
            confidence=1,
            accepted=True,
        )
        source = result(
            walers=self.chain_walers,
            struts=(strut("S0", 0, walers=("WL-A", "WR-A")), first, second,
                    strut("S2", 200, walers=("WL-B", "WR-B"))),
            candidates=(candidate,),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual(
            {frozenset(("S0", "S1-A", "S1-B", "S2"))},
            zoning_members(outcome),
        )

    def test_shared_unit_with_explicit_topology_conflict_stays_atomic_and_independent(self):
        walers = (*self.chain_walers, waler("XL", (20000, -1000), (20000, 2000)),
                  waler("XR", (30000, -1000), (30000, 2000)))
        first = strut("G-A", 100, walers=("WL-A", "WR-A"))
        second = strut(
            "G-B", 110, start_x=20000, end_x=30000, walers=("XL", "XR")
        )
        candidate = DoubleSupportCandidate(
            id="D1",
            first_strut_id=first.id,
            second_strut_id=second.id,
            centerline_spacing=10,
            angle_difference_deg=0,
            overlap_ratio=1,
            length_difference=0,
            confidence=1,
            accepted=True,
        )
        source = result(
            walers=walers,
            struts=(strut("S0", 0, walers=("WL-A", "WR-A")), first, second),
            candidates=(candidate,),
        )

        outcome = assign_initial_zoning(source)

        self.assertEqual(
            {frozenset(("S0",)), frozenset(("G-A", "G-B"))},
            zoning_members(outcome),
        )
        self.assertEqual(
            [INITIAL_ZONING_TOPOLOGY_CONFLICT],
            [item.code for item in outcome.diagnostics],
        )


class InitialZoningProjectBoundaryTests(unittest.TestCase):
    def _source(self):
        walers = (
            waler("WL", (0, -1000), (0, 1000)),
            waler("WR", (10000, -1000), (10000, 1000)),
        )
        return result(
            walers=walers,
            struts=(strut("S1", 0), strut("S2", 500)),
        )

    def test_recognition_result_is_unchanged_until_completed_mapping_boundary(self):
        source = self._source()

        self.assertTrue(all(not member.initial_zoning for member in source.struts))
        self.assertEqual(
            ["DXF", "DXF"],
            [row["Zoning"] for row in source.to_project_rows()["struts"]],
        )

        staged = ProjectService().stage_dxf_review_apply(ApplyDxfReviewRequest(
            current_project_data=ProjectDataModel(),
            current_workflow_status=DxfWorkflowStatus.REVIEW,
            import_mode="replace",
            review_result=source,
        ))

        self.assertEqual(
            ["DXF-Z1", "DXF-Z1"],
            [row["Zoning"] for row in staged.imported_rows["struts"]],
        )
        self.assertTrue(all(not member.initial_zoning for member in source.struts))

    def test_append_preserves_existing_zoning_and_avoids_name_collision(self):
        current = ProjectDataModel(
            struts=[{
                "StrutID": "S9",
                "StartX": 0,
                "StartY": 5000,
                "EndX": 10000,
                "EndY": 5000,
                "Zoning": "DXF-Z1",
            }],
        )

        staged = ProjectService().stage_dxf_review_apply(ApplyDxfReviewRequest(
            current_project_data=current,
            current_workflow_status=DxfWorkflowStatus.REVIEW,
            import_mode="append",
            review_result=self._source(),
        ))

        self.assertEqual("DXF-Z1", staged.project_data.struts[0]["Zoning"])
        self.assertEqual(
            ["DXF-Z2", "DXF-Z2"],
            [row["Zoning"] for row in staged.imported_rows["struts"]],
        )

    def test_confirmed_out_of_tolerance_shared_pair_imports_then_solver_rejects(self):
        walers = (
            waler("WL", (0, -1000), (0, 1000)),
            waler("WR", (10000, -1000), (10000, 1000)),
        )
        first = strut("S1-A", 0)
        second = strut("S1-B", 100, end_x=10100)
        candidate = DoubleSupportCandidate(
            id="D1",
            first_strut_id=first.id,
            second_strut_id=second.id,
            centerline_spacing=100,
            angle_difference_deg=0,
            overlap_ratio=1,
            length_difference=100,
            confidence=1,
            accepted=True,
        )
        source = result(
            walers=walers,
            struts=(first, second),
            candidates=(candidate,),
        )

        staged = ProjectService().stage_dxf_review_apply(ApplyDxfReviewRequest(
            current_project_data=ProjectDataModel(),
            current_workflow_status=DxfWorkflowStatus.REVIEW,
            import_mode="replace",
            review_result=source,
        ))

        self.assertEqual(
            staged.project_data.struts[0]["Zoning"],
            staged.project_data.struts[1]["Zoning"],
        )
        self.assertEqual(
            staged.project_data.struts[0]["SharedLayoutGroup"],
            staged.project_data.struts[1]["SharedLayoutGroup"],
        )
        with self.assertRaises(SolverInputBuildError) as caught:
            SupportInputBuilder().build_zone(
                staged.project_data,
                staged.project_data.struts[0]["Zoning"],
            )
        self.assertEqual(
            ["ZONING_LENGTH_OUT_OF_TOLERANCE"],
            [issue.code for issue in caught.exception.geometry_issues],
        )


if __name__ == "__main__":
    unittest.main()
