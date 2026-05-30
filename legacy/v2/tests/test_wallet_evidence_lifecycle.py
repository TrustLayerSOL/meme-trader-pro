import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_evidence_lifecycle import write_wallet_evidence_lifecycle_report
from wallets.wallet_evidence_lifecycle import build_wallet_evidence_lifecycle_report


def evidence(
    wallet: str,
    mint: str,
    action: str,
    timestamp: float,
    delta: float,
    signature: str,
) -> dict:
    return {
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": action,
        "timestamp": timestamp,
        "token_amount_delta": delta,
        "transaction_signature": signature,
        "confidence_score": 90,
    }


class WalletEvidenceLifecycleTests(unittest.TestCase):
    def test_builds_round_trip_lifecycle_without_price_assumptions(self):
        report = build_wallet_evidence_lifecycle_report(
            evidence_records=[
                evidence("WalletA", "MintA", "buy", 1000, 100.0, "SigBuy"),
                evidence("WalletA", "MintA", "sell", 1120, -100.0, "SigSell"),
            ],
            generated_at=1234.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "WALLET_EVIDENCE_LIFECYCLE_REVIEW_ONLY")
        lifecycle = report["lifecycles"][0]
        self.assertEqual(lifecycle["wallet"], "WalletA")
        self.assertEqual(lifecycle["token_mint"], "MintA")
        self.assertEqual(lifecycle["lifecycle_status"], "round_trip_observed")
        self.assertEqual(lifecycle["hold_duration_seconds"], 120.0)
        self.assertEqual(lifecycle["entry_signature"], "SigBuy")
        self.assertEqual(lifecycle["exit_signature"], "SigSell")
        self.assertEqual(lifecycle["net_token_amount_delta"], 0.0)
        self.assertNotIn("pnl", lifecycle)
        self.assertEqual(report["summary"]["round_trip_lifecycles"], 1)
        self.assertEqual(report["wallets"]["WalletA"]["average_hold_duration_seconds"], 120.0)

    def test_buy_only_and_sell_only_are_labeled_explicitly(self):
        report = build_wallet_evidence_lifecycle_report(
            evidence_records=[
                evidence("WalletA", "MintOpen", "buy", 1000, 10.0, "SigBuyOnly"),
                evidence("WalletB", "MintPrior", "sell", 1005, -5.0, "SigSellOnly"),
            ],
            generated_at=1234.0,
        )

        statuses = {row["token_mint"]: row["lifecycle_status"] for row in report["lifecycles"]}
        self.assertEqual(statuses["MintOpen"], "buy_only_open_or_unseen_exit")
        self.assertEqual(statuses["MintPrior"], "sell_only_missing_entry")
        self.assertEqual(report["summary"]["buy_only_lifecycles"], 1)
        self.assertEqual(report["summary"]["sell_only_lifecycles"], 1)

    def test_quote_mints_and_missing_timestamps_are_excluded_with_counts(self):
        report = build_wallet_evidence_lifecycle_report(
            evidence_records=[
                evidence("WalletA", "So11111111111111111111111111111111111111112", "buy", 1000, 1.0, "QuoteSig"),
                {"wallet": "WalletA", "token_mint": "MintMissingTime", "observed_action": "buy"},
                evidence("WalletA", "MintA", "buy", 1000, 1.0, "SigA"),
            ],
            generated_at=1234.0,
        )

        self.assertEqual(report["summary"]["input_evidence_rows"], 3)
        self.assertEqual(report["summary"]["skipped_quote_mint_rows"], 1)
        self.assertEqual(report["summary"]["skipped_missing_timestamp_rows"], 1)
        self.assertEqual(report["summary"]["lifecycle_rows"], 1)

    def test_writer_persists_lifecycle_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_evidence_lifecycle_report.json"
            report = write_wallet_evidence_lifecycle_report(
                out_path=out,
                evidence_records=[
                    evidence("WalletA", "MintA", "buy", 1000, 1.0, "SigA"),
                ],
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["lifecycle_rows"], 1)


if __name__ == "__main__":
    unittest.main()
