import unittest

from bracing_optimizer.algorithms.support import SupportConfig
from bracing_optimizer.presentation.dialogs.support_solver_dialog import (
    duplicate_support_limit_summary,
)


def config(support_id, *, target_jack_region=2):
    return SupportConfig(
        support_id=support_id,
        total_length=10_000,
        pile_centers=[2_000, 8_000],
        waler_centers=[0, 10_000],
        target_jack_region=target_jack_region,
        steel_lengths=[4_000, 5_000],
    )


class DuplicateSupportLimitSummaryTests(unittest.TestCase):
    def test_consecutive_supports_are_shown_as_a_clear_range(self):
        configs = [config(f"S{number}") for number in range(3, 11)]
        configs.append(config("S11", target_jack_region=3))

        self.assertEqual(
            duplicate_support_limit_summary(configs),
            "S3～S10 為同支撐限制",
        )

    def test_separate_runs_are_not_presented_as_one_continuous_range(self):
        configs = [config(support_id) for support_id in ("S3", "S4", "S7")]

        self.assertEqual(
            duplicate_support_limit_summary(configs),
            "S3～S4、S7 為同支撐限制",
        )

    def test_unique_configurations_do_not_show_a_reminder(self):
        configs = [
            config("S1", target_jack_region=1),
            config("S2", target_jack_region=2),
        ]

        self.assertEqual(duplicate_support_limit_summary(configs), "")


if __name__ == "__main__":
    unittest.main()
