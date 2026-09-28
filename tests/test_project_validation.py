import copy
import unittest

from bracing_optimizer.application.project_data import ProjectDataModel
from bracing_optimizer.application.project_validation import ProjectDataValidator


class ProjectDataValidatorTests(unittest.TestCase):
    def test_validation_reports_row_location_without_mutating_project(self):
        model = ProjectDataModel(
            walers=[{
                "WalerID": "W1",
                "StartX": 0,
                "StartY": 0,
                "EndX": 1000,
                "EndY": 0,
            }],
            struts=[{
                "StrutID": "S1",
                "FromWaler": "W1",
                "StartX": 2000,
                "StartY": 0,
                "EndX": 2000,
                "EndY": 1000,
                "ColumnPositions": "500,500",
            }],
        )
        before = copy.deepcopy(model.to_case_data())

        report = ProjectDataValidator().validate(model)

        self.assertFalse(report.valid)
        self.assertTrue(any(
            issue.table == "struts"
            and issue.row_index == 1
            and "起點未落於圍令" in issue.message
            for issue in report.errors
        ))
        self.assertTrue(any(
            issue.table == "struts" and "中間柱位置重複" in issue.message
            for issue in report.warnings
        ))
        self.assertEqual(model.to_case_data(), before)

    def test_empty_project_uses_data_only_report(self):
        report = ProjectDataValidator().validate(ProjectDataModel())

        self.assertTrue(report.valid)
        self.assertEqual(report.errors, ())
        self.assertEqual(report.warnings, ())

    def test_project_validation_does_not_enforce_solver_zoning_tolerances(self):
        model = ProjectDataModel(
            walers=[
                {"WalerID": "W1", "StartX": 0, "StartY": -10000,
                 "EndX": 0, "EndY": 10000},
                {"WalerID": "W2", "StartX": 10000, "StartY": -10000,
                 "EndX": 10000, "EndY": 10000},
            ],
            struts=[
                {"StrutID": "S1", "FromWaler": "W1", "ToWaler": "W2",
                 "StartX": 0, "StartY": 0, "EndX": 10000, "EndY": 0,
                 "Zoning": "Z1"},
                {"StrutID": "S2", "FromWaler": "W1", "ToWaler": "W2",
                 "StartX": 0, "StartY": 1000, "EndX": 10000, "EndY": 2000,
                 "Zoning": "Z1"},
            ],
        )

        report = ProjectDataValidator().validate(model)

        self.assertTrue(report.valid, [issue.message for issue in report.errors])
        self.assertFalse(any(
            "5°" in issue.message or "5 mm" in issue.message
            for issue in (*report.errors, *report.warnings)
        ))


if __name__ == "__main__":
    unittest.main()
