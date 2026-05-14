import json
import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_outcome_ledger import build_records
from wallets.wallet_outcome_ledger import build_wallet_outcome_ledger


class WalletSignalBackfillTests(unittest.TestCase):
    def test_build_records_includes_wallet_performance_signals_as_unknown_outcome_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paper = root / "paper.json"
            rejections = root / "rejections.jsonl"
            performance = root / "wallet_performance.json"
            paper.write_text(json.dumps({"open_trades": [], "closed_trades": [], "failed_trades": []}))
            rejections.write_text("")
            performance.write_text(
                json.dumps(
                    {
                        "signals": [
                            {
                                "mint": "MintA",
                                "wallets": ["WalletA", "WalletB"],
                                "score": 48,
                                "signal_type": "weighted_early_signal",
                                "token_age_seconds": 72,
                                "should_trade": False,
                            }
                        ]
                    }
                )
            )

            records = build_records(
                paper_path=paper,
                rejection_path=rejections,
                performance_path=performance,
            )
            ledger = build_wallet_outcome_ledger(records)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"], "wallet_performance_signal")
        self.assertEqual(records[0]["later_token_outcome"]["outcome_type"], "unknown")
        self.assertEqual(ledger["counts"]["wallets"], 2)
        self.assertEqual(ledger["wallets"]["WalletA"]["known_outcomes"], 0)


if __name__ == "__main__":
    unittest.main()
