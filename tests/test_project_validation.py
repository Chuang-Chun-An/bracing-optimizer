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


if __name__ == "__main__":
    unittest.main()
