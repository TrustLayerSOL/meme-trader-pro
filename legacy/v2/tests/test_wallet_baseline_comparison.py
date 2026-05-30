import unittest

from wallets.wallet_baseline_comparison import compare_wallet_reports


class WalletBaselineComparisonTests(unittest.TestCase):
    def test_marks_matching_recommendations_as_agreement(self):
        report = compare_wallet_reports(
            quant_report={
                "wallets": [
                    {
                        "wallet": "WalletA",
                        "tier": "trusted",
                        "paper_watch_entries": 30,
                        "recommendation": {"action": "DEMOTION_REVIEW"},
                    }
                ]
            },
            outcome_ledger={
                "wallets": {
                    "WalletA": {
                        "wallet": "WalletA",
                        "known_outcomes": 25,
                        "recommendation": {"action": "DEMOTION_REVIEW"},
                    }
                }
            },
        )

        self.assertEqual(report["counts"]["overlap"], 1)
        self.assertEqual(report["comparison_counts"]["AGREEMENT"], 1)
        self.assertEqual(report["wallets"][0]["comparison_status"], "AGREEMENT")

    def test_quant_action_without_enough_outcome_evidence_is_unconfirmed(self):
        report = compare_wallet_reports(
            quant_report={
                "wallets": [
                    {
                        "wallet": "WalletB",
                        "tier": "trusted",
                        "paper_watch_entries": 8,
                        "recommendation": {"action": "DEMOTION_REVIEW"},
                    }
                ]
            },
            outcome_ledger={
                "wallets": {
                    "WalletB": {
                        "wallet": "WalletB",
                        "known_outcomes": 3,
                        "recommendation": {"action": "HOLD_MORE_DATA"},
                    }
                }
            },
        )

        self.assertEqual(report["comparison_counts"]["QUANT_SIGNAL_UNCONFIRMED"], 1)
        self.assertIn("outcome ledger has too little known evidence", report["wallets"][0]["reasons"])

    def test_counts_quant_only_and_ledger_only_wallets(self):
        report = compare_wallet_reports(
            quant_report={
                "wallets": [
                    {"wallet": "QuantOnly", "recommendation": {"action": "HOLD_MORE_DATA"}},
                    {"wallet": "Both", "recommendation": {"action": "HOLD_MORE_DATA"}},
                ]
            },
            outcome_ledger={
                "wallets": {
                    "LedgerOnly": {"wallet": "LedgerOnly", "recommendation": {"action": "HOLD_MORE_DATA"}},
                    "Both": {"wallet": "Both", "recommendation": {"action": "HOLD_MORE_DATA"}},
                }
            },
        )

        self.assertEqual(report["counts"]["quant_only"], 1)
        self.assertEqual(report["counts"]["ledger_only"], 1)
        self.assertEqual(report["counts"]["overlap"], 1)
        self.assertEqual(report["comparison_counts"]["QUANT_ONLY"], 1)
        self.assertEqual(report["comparison_counts"]["LEDGER_ONLY"], 1)

    def test_matching_hold_more_data_stays_hold_more_data(self):
        report = compare_wallet_reports(
            quant_report={"wallets": [{"wallet": "WalletC", "recommendation": {"action": "HOLD_MORE_DATA"}}]},
            outcome_ledger={
                "wallets": {
                    "WalletC": {
                        "wallet": "WalletC",
                        "known_outcomes": 2,
                        "recommendation": {"action": "HOLD_MORE_DATA"},
                    }
                }
            },
        )

        self.assertEqual(report["wallets"][0]["comparison_status"], "HOLD_MORE_DATA")


if __name__ == "__main__":
    unittest.main()
