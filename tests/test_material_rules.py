import ast
import unittest
from pathlib import Path

from bracing_optimizer.algorithms import wales
from bracing_optimizer.domain import material_rules


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MaterialLengthRuleTests(unittest.TestCase):
    def test_established_boundaries_are_preserved(self):
        expected = {
            3999: "out",
            4000: "short",
            5999: "short",
            6000: "mid",
            8000: "mid",
            8001: "long",
            10000: "long",
            10001: "out",
        }

        self.assertEqual(
            {length: material_rules.classify_length(length) for length in expected},
            expected,
        )

    def test_ratio_targets_are_normalized(self):
        targets = material_rules.MaterialRatioTargets.normalized(38, 40, 22)

        self.assertEqual(
            targets.as_dict(),
            {"short": 0.38, "mid": 0.40, "long": 0.22},
        )

    def test_ratio_targets_reject_invalid_values(self):
        for values in (
            (0, 0, 0),
            (-1, 1, 1),
            (float("nan"), 1, 1),
            (float("inf"), 1, 1),
        ):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    material_rules.MaterialRatioTargets.normalized(*values)

    def test_ratio_analysis_counts_only_classified_lengths(self):
        analysis = material_rules.analyze_material_ratios(
            [3999, 4000, 6000, 8000, 8001, 10001],
            material_rules.MaterialRatioTargets.normalized(1, 2, 1),
            weight=100,
        )

        self.assertEqual(
            analysis.counts,
            {"short": 1, "mid": 2, "long": 1},
        )
        self.assertEqual(analysis.classified_total, 4)
        self.assertEqual(analysis.out_count, 2)
        self.assertAlmostEqual(analysis.ratio_deviation, 0.0)
        self.assertAlmostEqual(analysis.penalty, 0.0)

    def test_ratio_analysis_handles_no_classified_materials(self):
        analysis = material_rules.analyze_material_ratios(
            [1000, 12000],
            material_rules.MaterialRatioTargets.normalized(1, 1, 1),
            weight=90,
        )

        self.assertEqual(analysis.classified_total, 0)
        self.assertEqual(analysis.out_count, 2)
        self.assertEqual(
            analysis.ratios,
            {"short": 0.0, "mid": 0.0, "long": 0.0},
        )
        self.assertAlmostEqual(analysis.ratio_deviation, 1.0)
        self.assertAlmostEqual(analysis.penalty, 90.0)

    def test_waler_compatibility_wrapper_uses_configured_boundaries(self):
        config = wales.Config(total_length=0, support_points=[])
        config.short_segment_min = 100
        config.short_segment_max = 200
        config.mid_segment_min = 200
        config.mid_segment_max = 300
        config.long_segment_min = 300
        config.long_segment_max = 400

        self.assertEqual(wales.classify_length(150, config), "short")
        self.assertEqual(wales.classify_length(200, config), "mid")
        self.assertEqual(wales.classify_length(301, config), "long")


class SolverDependencyRuleTests(unittest.TestCase):
    @staticmethod
    def _imported_roots(module_path: Path) -> set[str]:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".", 1)[0])
        return roots

    def test_support_does_not_depend_on_wales(self):
        imports = self._imported_roots(
            PROJECT_ROOT / "bracing_optimizer" / "algorithms" / "support.py"
        )

        self.assertNotIn("wales", imports)

    def test_material_rules_does_not_depend_on_either_solver(self):
        imports = self._imported_roots(
            PROJECT_ROOT / "bracing_optimizer" / "domain" / "material_rules.py"
        )

        self.assertTrue({"support", "wales"}.isdisjoint(imports))

    def test_wales_does_not_depend_on_tkinter(self):
        imports = self._imported_roots(
            PROJECT_ROOT / "bracing_optimizer" / "algorithms" / "wales.py"
        )

        self.assertNotIn("tkinter", imports)


if __name__ == "__main__":
    unittest.main()
