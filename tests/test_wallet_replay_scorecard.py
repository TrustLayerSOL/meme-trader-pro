import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wallets.wallet_replay_scorecard import build_wallet_replay_scorecard
from utils.build_wallet_replay_scorecard import write_wallet_replay_scorecard


def event(wallets, *, mint="MintA", fill_status="fillable_with_assumptions", regime=None, windows=None):
    return {
        "event_id": f"dec-{mint}",
        "mint": mint,
        "wallets": [{"wallet": wallet} for wallet in wallets],
        "decision_context": {
            "cluster": {"wallet_count": len(wallets), "duration_seconds": 7},
            "market_regime": {"tags": regime or ["runner_heavy"]},
        },
        "execution_assumptions": {"fill_status": fill_status},
        "later_outcome": {
            "windows": windows
            or {
                "30s": {"outcome_type": "runner"},
                "2m": {"outcome_type": "runner"},
                "5m": {"outcome_type": "loser"},
                "15m": {"outcome_type": "loser"},
            }
        },
    }


class WalletReplayScorecardTests(unittest.TestCase):
    def test_scorecard_tracks_window_outcomes_fillability_and_regimes(self):
        report = build_wallet_replay_scorecard(
            [
                event(["WalletA", "WalletB"], mint="Runner1", regime=["runner_heavy"]),
                event(
                    ["WalletA"],
                    mint="Rug1",
                    regime=["rug_heavy"],
                    windows={
                        "30s": {"outcome_type": "unknown"},
                        "2m": {"outcome_type": "rug"},
                        "5m": {"outcome_type": "rug"},
                        "15m": {"outcome_type": "rug"},
                    },
                ),
                event(["WalletA", "WalletB"], mint="NoFill", fill_status="failed_liquidity_floor"),
            ]
        )

        wallet = report["wallets"]["WalletA"]

        self.assertEqual(report["mode"], "WALLET_REPLAY_SCORECARD_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(wallet["total_events"], 3)
        self.assertEqual(wallet["fillable_events"], 2)
        self.assertEqual(wallet["failed_liquidity_events"], 1)
        self.assertEqual(wallet["regime_breakdown"]["runner_heavy"], 2)
        self.assertEqual(wallet["regime_breakdown"]["rug_heavy"], 1)
        self.assertEqual(wallet["windows"]["30s"]["runner"], 2)
        self.assertEqual(wallet["windows"]["2m"]["rug"], 1)
        self.assertEqual(wallet["windows"]["15m"]["known"], 3)
        self.assertGreater(wallet["signal_quality"]["known_rate_15m"], 0)

    def test_scorecard_tracks_repeated_co_entry_partners_and_pairs(self):
        report = build_wallet_replay_scorecard(
            [
                event(["WalletA", "WalletB"], mint="A"),
                event(["WalletA", "WalletB"], mint="B"),
                event(["WalletA", "WalletC"], mint="C"),
            ]
        )

        wallet = report["wallets"]["WalletA"]

        self.assertEqual(wallet["co_entry_partners"][0], {"wallet": "WalletB", "count": 2})
        self.assertEqual(wallet["co_entry_partners"][1], {"wallet": "WalletC", "count": 1})
        self.assertEqual(report["ecosystems"]["top_co_entry_pairs"][0], {"wallets": ["WalletA", "WalletB"], "count": 2})
        self.assertEqual(report["ecosystems"]["repeated_pair_count"], 1)

    def test_scorecard_separates_coverage_from_performance(self):
        report = build_wallet_replay_scorecard(
            [
                event(
                    ["WalletA"],
                    mint="Unknown",
                    windows={
                        "30s": {"outcome_type": "unknown"},
                        "2m": {"outcome_type": "unknown"},
                        "5m": {"outcome_type": "unknown"},
                        "15m": {"outcome_type": "unknown"},
                    },
                )
            ]
        )

        wallet = report["wallets"]["WalletA"]

        self.assertEqual(wallet["windows"]["15m"]["known"], 0)
        self.assertEqual(wallet["signal_quality"]["known_rate_15m"], 0)
        self.assertEqual(wallet["signal_quality"]["review_status"], "insufficient_replay_coverage")

    def test_writer_creates_scorecard_json(self):
        with TemporaryDirectory() as tmp:
            out = Path(tmp) / "scorecard.json"
            result = write_wallet_replay_scorecard([event(["WalletA"], mint="A")], out_path=out)

            self.assertEqual(result["out_path"], str(out))
            self.assertEqual(result["counts"]["wallets"], 1)
            self.assertTrue(out.exists())
            self.assertIn("WalletA", out.read_text())


if __name__ == "__main__":
    unittest.main()
