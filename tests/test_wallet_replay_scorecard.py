import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from wallets.wallet_replay_scorecard import build_wallet_replay_scorecard
from wallets.wallet_replay_review import build_wallet_replay_review
from wallets.wallet_replay_review import render_wallet_replay_review_markdown
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

    def test_replay_review_separates_reviewable_wallets_from_low_coverage(self):
        scorecard = build_wallet_replay_scorecard(
            [
                event(["WalletGood", "WalletPartner"], mint="Good1"),
                event(["WalletGood", "WalletPartner"], mint="Good2"),
                event(["WalletGood"], mint="Good3"),
                event(["WalletGood"], mint="Good4"),
                event(["WalletGood"], mint="Good5"),
                event(
                    ["WalletThin"],
                    mint="Thin1",
                    windows={
                        "30s": {"outcome_type": "unknown"},
                        "2m": {"outcome_type": "unknown"},
                        "5m": {"outcome_type": "unknown"},
                        "15m": {"outcome_type": "unknown"},
                    },
                ),
            ]
        )

        review = build_wallet_replay_review(scorecard, limit=10, min_known_events=3, min_fillable_events=3)

        self.assertEqual(review["mode"], "WALLET_REPLAY_REVIEW_ONLY")
        self.assertTrue(review["live_execution_locked"])
        self.assertEqual(review["summary"]["reviewable_wallets"], 1)
        self.assertEqual(review["summary"]["low_coverage_wallets"], 2)
        self.assertEqual(review["reviewable_wallets"][0]["wallet"], "WalletGood")
        self.assertEqual(review["reviewable_wallets"][0]["known_15m"], 5)
        self.assertIn("WalletThin", {row["wallet"] for row in review["low_coverage_wallets"]})
        self.assertEqual(review["co_entry_review"][0]["wallets"], ["WalletGood", "WalletPartner"])

    def test_replay_review_markdown_is_human_readable(self):
        scorecard = build_wallet_replay_scorecard(
            [
                event(["WalletGood", "WalletPartner"], mint="Good1"),
                event(["WalletGood", "WalletPartner"], mint="Good2"),
                event(["WalletGood"], mint="Good3"),
                event(["WalletThin"], mint="Thin1", windows={"15m": {"outcome_type": "unknown"}}),
            ]
        )
        review = build_wallet_replay_review(scorecard, limit=10, min_known_events=2, min_fillable_events=2)

        markdown = render_wallet_replay_review_markdown(review)

        self.assertIn("# Wallet Replay Ecosystem Review", markdown)
        self.assertIn("Review-only", markdown)
        self.assertIn("## Reviewable Wallets", markdown)
        self.assertIn("WalletGood", markdown)
        self.assertIn("## Low-Coverage Wallets", markdown)
        self.assertIn("WalletThin", markdown)
        self.assertIn("## Repeated Co-Entry Pairs", markdown)
        self.assertIn("WalletPartner", markdown)

    def test_replay_review_adds_conservative_machine_recommendations(self):
        promotion_events = [
            event(
                ["WalletPromote"],
                mint=f"Promote{i}",
                windows={
                    "30s": {"outcome_type": "runner"},
                    "2m": {"outcome_type": "runner"},
                    "5m": {"outcome_type": "runner"},
                    "15m": {"outcome_type": "runner"},
                },
            )
            for i in range(12)
        ]
        demotion_events = [
            event(
                ["WalletDemote"],
                mint=f"Demote{i}",
                windows={
                    "30s": {"outcome_type": "rug"},
                    "2m": {"outcome_type": "rug"},
                    "5m": {"outcome_type": "rug"},
                    "15m": {"outcome_type": "rug"},
                },
            )
            for i in range(10)
        ]
        hold_events = [event(["WalletHold"], mint=f"Hold{i}") for i in range(5)]

        review = build_wallet_replay_review(
            build_wallet_replay_scorecard(promotion_events + demotion_events + hold_events),
            limit=20,
            min_known_events=5,
            min_fillable_events=5,
        )
        decisions = {row["wallet"]: row["recommended_decision"] for row in review["decision_recommendations"]}

        self.assertEqual(decisions["WalletPromote"]["action"], "PROMOTION_REVIEW")
        self.assertEqual(decisions["WalletDemote"]["action"], "DEMOTION_REVIEW")
        self.assertEqual(decisions["WalletHold"]["action"], "HOLD_MORE_DATA")
        self.assertFalse(decisions["WalletPromote"]["auto_apply"])
        self.assertEqual(review["decision_summary"]["promotion_review"], 1)
        self.assertEqual(review["decision_summary"]["demotion_review"], 1)
        self.assertIn("Best Educated Decisions", review["operator_report_markdown"])


if __name__ == "__main__":
    unittest.main()
