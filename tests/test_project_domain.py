import copy
import unittest

from bracing_optimizer.application.project_data import (
    ProjectDataModel,
    normalize_project_row,
)
from bracing_optimizer.application.project_mapper import ProjectDomainMappingError
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder


class ProjectDomainTests(unittest.TestCase):
    @staticmethod
    def model() -> ProjectDataModel:
        return ProjectDataModel(
            struts=[{
                "StrutID": "S1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 10000,
                "EndY": 0,
                "ColumnPositions": "2500,7200",
                "BeamPositions": "4800",
                "AssociatedColumnIDs": "C1,C2",
                "AssociatedBeamIDs": "BM1",
            }],
        )

    def test_strut_owns_typed_column_and_beam_positions(self):
        model = self.model()

        domain = model.to_domain()

        self.assertEqual(domain.struts[0].column_positions, (2500.0, 7200.0))
        self.assertEqual(domain.struts[0].beam_positions, (4800.0,))
        self.assertFalse(hasattr(domain, "columns"))
        self.assertFalse(hasattr(domain, "beams"))
        self.assertFalse(hasattr(domain, "strut_obstacles"))

    def test_domain_projection_is_read_only(self):
        model = self.model()
        before = copy.deepcopy(model.to_case_data())

        model.to_domain()

        self.assertEqual(model.to_case_data(), before)

    def test_current_row_normalization_does_not_modify_source_mapping(self):
        source = self.model().struts[0]
        before = copy.deepcopy(source)

        normalized = normalize_project_row("struts", source)

        self.assertEqual(source, before)
        self.assertEqual(normalized, before)
        self.assertIsNot(normalized, source)

    def test_support_solver_reads_positions_from_owning_strut(self):
        config = SupportInputBuilder().build_one(self.model(), "S1")

        self.assertEqual(config.pile_centers, [2500, 7200])
        self.assertEqual(config.waler_centers, [4800])

    def test_strict_domain_projection_rejects_duplicate_entity_ids(self):
        model = ProjectDataModel(
            walers=[
                {"WalerID": "W1"},
                {"WalerID": "W1"},
            ],
        )

        with self.assertRaises(ProjectDomainMappingError):
            model.to_domain(strict=True)


if __name__ == "__main__":
    unittest.main()
