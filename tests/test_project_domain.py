import copy
import unittest

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_mapper import ProjectDomainMappingError
from bracing_optimizer.application.solver_input_builder import SupportInputBuilder
from bracing_optimizer.infrastructure.project_persistence import (
    ProjectPersistenceError,
    ProjectSerializer,
)
from tools.upgrade_project_schema import upgrade_payload


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


class ProjectSchemaUpgradeTests(unittest.TestCase):
    @staticmethod
    def old_payload() -> dict:
        return {
            "schema_version": 2,
            "input_data": {
                "walers": [],
                "struts": [{
                    "StrutID": "S1",
                    "StartX": 0,
                    "StartY": 0,
                    "EndX": 1000,
                    "EndY": 0,
                    "ColumnPositions": "250",
                    "BeamPositions": "750",
                }],
                "braces": [],
            },
            "dxf_import_state": {
                "converted": {
                    "columns": [{"id": "C1"}],
                    "beams": [{"id": "BM1"}],
                }
            },
        }

    def test_upgrade_keeps_positions_on_strut_without_entity_tables(self):
        upgraded = upgrade_payload(self.old_payload())

        ProjectSerializer.validate(upgraded)
        data = upgraded["input_data"]
        self.assertEqual(upgraded["schema_version"], 3)
        self.assertEqual(data["struts"][0]["ColumnPositions"], "250")
        self.assertEqual(data["struts"][0]["BeamPositions"], "750")
        self.assertNotIn("columns", data)
        self.assertNotIn("beams", data)
        self.assertNotIn("strut_obstacles", data)

    def test_upgrade_converts_legacy_numbered_position_fields(self):
        payload = self.old_payload()
        row = payload["input_data"]["struts"][0]
        row.pop("ColumnPositions")
        row.pop("BeamPositions")
        row.update(Column1=200, Column2=800, Beam1=500, Beam2="")

        upgraded = upgrade_payload(payload)
        upgraded_row = upgraded["input_data"]["struts"][0]

        self.assertEqual(upgraded_row["ColumnPositions"], "200,800")
        self.assertEqual(upgraded_row["BeamPositions"], "500")
        self.assertNotIn("Column1", upgraded_row)
        self.assertNotIn("Beam1", upgraded_row)

    def test_schema_rejects_invalid_strut_position(self):
        upgraded = upgrade_payload(self.old_payload())
        upgraded["input_data"]["struts"][0]["ColumnPositions"] = "wrong"

        with self.assertRaises(ProjectPersistenceError) as raised:
            ProjectSerializer.validate(upgraded)

        self.assertEqual(raised.exception.stage, "Domain 驗證失敗")


if __name__ == "__main__":
    unittest.main()
