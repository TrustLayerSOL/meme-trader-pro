import unittest

from research.signal_schema import build_signal_outcome_record
from wallets.wallet_outcome_ledger import build_wallet_outcome_ledger, wallet_outcome_row


def context(wallets, mint="MintA", liquidity=10_000, token_age=45, regime=None):
    return {
        "mint": mint,
        "decision_id": f"dec-{mint}",
        "source": "test",
        "signal_type": "wallet_cluster",
        "paper_lane": "main",
        "triggering_wallets": [{"wallet": wallet, "score": 70} for wallet in wallets],
        "cluster": {"wallet_count": len(wallets), "duration_seconds": 9},
        "market": {
            "liquidity": liquidity,
            "market_cap": 40_000,
            "token_age_seconds": token_age,
        },
        "market_regime": {"tags": regime or ["strong_runner_environment"]},
        "execution_assumptions": {"estimated_slippage_pct": 2.0, "delay_seconds": 1.2},
        "risk": {"risk_label": "LOW", "hard_block": False},
    }


class WalletOutcomeLedgerTests(unittest.TestCase):
    def test_ledger_combines_accepted_and_rejected_records_per_wallet(self):
        records = [
            build_signal_outcome_record(
                signal_context=context(["WalletA", "WalletB"], "WinMint"),
                decision={"should_trade": True, "action": "paper_open_attempt"},
                later_token_outcome={"status": "closed", "pnl_pct": 60, "runner": True},
            ),
            build_signal_outcome_record(
                signal_context=context(["WalletA"], "SkipMint", liquidity=1_200, regime=["low_liquidity_market"]),
                decision={"should_trade": False, "action": "skip", "reason": "liquidity too low"},
                later_token_outcome={"status": "unknown"},
                rejection_reason="liquidity too low",
            ),
        ]

        ledger = build_wallet_outcome_ledger(records)
        wallet = ledger["wallets"]["WalletA"]

        self.assertEqual(wallet["total_signals"], 2)
        self.assertEqual(wallet["accepted_signals"], 1)
        self.assertEqual(wallet["rejected_signals"], 1)
        self.assertEqual(wallet["known_outcomes"], 1)
        self.assertEqual(wallet["runner_participation"], 1)
        self.assertEqual(wallet["average_pnl_after_signal"], 60)
        self.assertEqual(wallet["market_regime_breakdown"]["strong_runner_environment"], 1)
        self.assertEqual(wallet["market_regime_breakdown"]["low_liquidity_market"], 1)

    def test_confidence_and_scores_are_review_only_and_sample_aware(self):
        row = wallet_outcome_row(
            "WalletA",
            [
                build_signal_outcome_record(
                    signal_context=context(["WalletA"], "A"),
                    decision={"should_trade": True},
                    later_token_outcome={"status": "closed", "pnl_pct": 25, "runner": True},
                ),
                build_signal_outcome_record(
                    signal_context=context(["WalletA"], "B", regime=["rug_heavy_environment"]),
                    decision={"should_trade": True},
                    later_token_outcome={"status": "closed", "pnl_pct": -40, "rug": True},
                ),
            ],
        )

        self.assertTrue(row["review_only"])
        self.assertEqual(row["confidence"]["sample_quality"], "thin")
        self.assertGreater(row["demotion_score"], 0)
        self.assertGreater(row["promotion_score"], 0)

    def test_labeled_outcome_counts_as_known_even_when_source_status_is_unknown(self):
        row = wallet_outcome_row(
            "WalletA",
            [
                build_signal_outcome_record(
                    signal_context=context(["WalletA"], "A"),
                    decision={"should_trade": True},
                    later_token_outcome={"status": "unknown", "pnl_pct": 40},
                ),
            ],
        )

        self.assertEqual(row["known_outcomes"], 1)
        self.assertEqual(row["runner_participation"], 1)

    def test_empty_ledger_is_valid_review_artifact(self):
        ledger = build_wallet_outcome_ledger([])

        self.assertEqual(ledger["mode"], "WALLET_OUTCOME_LEDGER_REVIEW_ONLY")
        self.assertTrue(ledger["live_execution_locked"])
        self.assertEqual(ledger["counts"]["wallets"], 0)


if __name__ == "__main__":
    unittest.main()
