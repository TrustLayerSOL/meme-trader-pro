import unittest

from research.outcome_linker import build_later_outcome_from_snapshots, build_windowed_outcomes_from_snapshots


class OutcomeLinkerTests(unittest.TestCase):
    def test_links_later_snapshots_as_runner_without_changing_decision_context(self):
        outcome = build_later_outcome_from_snapshots(
            mint="MintA",
            signal_time=100,
            snapshots=[
                {"time": 90, "price": 0.01, "liquidity": 10_000},
                {"time": 101, "price": 0.01, "liquidity": 10_000},
                {"time": 130, "price": 0.018, "liquidity": 14_000},
                {"time": 160, "price": 0.015, "liquidity": 13_000},
            ],
        )

        self.assertEqual(outcome["outcome_type"], "runner")
        self.assertTrue(outcome["runner"])
        self.assertEqual(outcome["entry_price"], 0.01)
        self.assertEqual(outcome["exit_price"], 0.015)
        self.assertGreaterEqual(outcome["max_favorable_excursion_pct"], 80)
        self.assertEqual(outcome["snapshot_count"], 3)

    def test_returns_unknown_when_no_later_snapshots_exist(self):
        outcome = build_later_outcome_from_snapshots(
            mint="MintA",
            signal_time=100,
            snapshots=[{"time": 90, "price": 0.01, "liquidity": 10_000}],
        )

        self.assertEqual(outcome["outcome_type"], "unknown")
        self.assertFalse(outcome["runner"])
        self.assertEqual(outcome["classification_reasons"], ["no later snapshots available"])

    def test_liquidity_collapse_is_labeled_as_rug(self):
        outcome = build_later_outcome_from_snapshots(
            mint="MintA",
            signal_time=100,
            snapshots=[
                {"time": 101, "price": 0.01, "liquidity": 20_000},
                {"time": 150, "price": 0.001, "liquidity": 1_500, "risk_label": "EMERGENCY"},
            ],
        )

        self.assertEqual(outcome["outcome_type"], "rug")
        self.assertTrue(outcome["rug"])
        self.assertLessEqual(outcome["liquidity_change_pct"], -90)

    def test_builds_fixed_window_outcomes_from_later_snapshots(self):
        windows = build_windowed_outcomes_from_snapshots(
            mint="MintA",
            signal_time=100,
            snapshots=[
                {"time": 101, "price": 0.01, "liquidity": 10_000},
                {"time": 125, "price": 0.018, "liquidity": 12_000},
                {"time": 210, "price": 0.012, "liquidity": 11_000},
                {"time": 390, "price": 0.006, "liquidity": 9_000},
                {"time": 980, "price": 0.001, "liquidity": 900, "risk_label": "EMERGENCY"},
            ],
        )

        self.assertEqual(list(windows.keys()), ["30s", "2m", "5m", "15m"])
        self.assertEqual(windows["30s"]["outcome_type"], "runner")
        self.assertEqual(windows["2m"]["outcome_type"], "runner")
        self.assertEqual(windows["5m"]["outcome_type"], "runner")
        self.assertLess(windows["5m"]["pnl_pct"], 0)
        self.assertEqual(windows["15m"]["outcome_type"], "rug")
        self.assertEqual(windows["15m"]["evaluation_horizon_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
