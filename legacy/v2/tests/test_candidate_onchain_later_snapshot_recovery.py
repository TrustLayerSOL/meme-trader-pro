import json
import tempfile
import unittest
from pathlib import Path

from utils.build_candidate_onchain_later_snapshot_recovery import write_candidate_onchain_later_snapshot_recovery
from wallets.candidate_onchain_later_snapshot_recovery import build_candidate_onchain_later_snapshot_recovery


WSOL = "So11111111111111111111111111111111111111112"


def token_balance(owner, mint, amount):
    return {
        "owner": owner,
        "mint": mint,
        "uiTokenAmount": {"uiAmount": amount, "uiAmountString": str(amount)},
    }


def raw_tx(*, signature="LaterSig", wallet="WalletA", mint="MintA", pool_owner="PoolA", block_time=130):
    return {
        "signature": signature,
        "token_mint": mint,
        "transaction": {
            "blockTime": block_time,
            "meta": {
                "preTokenBalances": [
                    token_balance(wallet, mint, 1_000),
                    token_balance(wallet, WSOL, 9.5),
                    token_balance(pool_owner, mint, 500_000),
                    token_balance(pool_owner, WSOL, 20.0),
                ],
                "postTokenBalances": [
                    token_balance(wallet, mint, 1_000),
                    token_balance(wallet, WSOL, 9.5),
                    token_balance(pool_owner, mint, 300_000),
                    token_balance(pool_owner, WSOL, 30.0),
                ],
            },
            "transaction": {"signatures": [signature]},
        },
    }


def anchor_record(wallet="WalletA", mint="MintA", event="EventA"):
    return {
        "event_id": event,
        "wallet": wallet,
        "token_mint": mint,
        "observed_action": "buy",
        "signal_time": 100.0,
        "transaction_signature": "EntrySig",
        "decision_context": {
            "estimated_entry_context": {
                "price": 0.00004,
                "liquidity": 80.0,
                "quote_mint": WSOL,
                "execution_price_quote": 0.00004,
                "decision_time_safe": True,
            }
        },
        "later_token_outcome": {"outcome_type": "unknown", "windows": {}},
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


def deferred_row(wallet="WalletA", mint="MintA", event="EventA"):
    return {
        "event_id": event,
        "wallet_address": wallet,
        "token_address": mint,
        "signal_time": 100.0,
        "needed_snapshot_start": 100.0,
        "needed_snapshot_end": 1000.0,
        "recommended_next_action": "archival_or_onchain_later_snapshot_recovery",
    }


class CandidateOnchainLaterSnapshotRecoveryTests(unittest.TestCase):
    def test_recovers_known_15m_outcome_from_anchor_and_later_raw_transaction(self):
        report = build_candidate_onchain_later_snapshot_recovery(
            deferred_rows=[deferred_row()],
            anchor_records=[anchor_record()],
            raw_transactions=[raw_tx()],
            quote_price_series=[{"timestamp": 99, "price_usd": 1.0}],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["deferred_rows_scanned"], 1)
        self.assertEqual(report["summary"]["candidate_records_built"], 1)
        self.assertEqual(report["summary"]["known_15m_outcomes_added"], 1)
        self.assertEqual(report["summary"]["blocked_missing_anchor_rows"], 0)
        result = report["records"][0]
        self.assertEqual(result["status"], "onchain_later_outcome_labeled")
        self.assertEqual(result["later_token_outcome"]["windows"]["15m"]["outcome_type"], "runner")
        self.assertEqual(report["summary"]["recovered_forward_records"], 1)
        recovered = report["recovered_forward_records"][0]
        self.assertEqual(recovered["status"], "candidate_onchain_later_outcome_recovered")
        self.assertEqual(recovered["outcome_window_labels"]["15m"]["outcome_type"], "runner")
        self.assertEqual(recovered["block_reasons"], [])
        self.assertTrue(recovered["candidate_onchain_later_snapshot_recovery"]["review_only"])
        self.assertEqual(report["summary"]["combined_repaired_records"], 1)
        self.assertEqual(report["combined_repaired_records"][0]["status"], "candidate_onchain_later_outcome_recovered")
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_missing_anchor_rows_are_reported_without_recovery(self):
        report = build_candidate_onchain_later_snapshot_recovery(
            deferred_rows=[deferred_row(event="Missing")],
            anchor_records=[],
            raw_transactions=[raw_tx()],
            quote_price_series=[{"timestamp": 99, "price_usd": 1.0}],
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["candidate_records_built"], 0)
        self.assertEqual(report["summary"]["blocked_missing_anchor_rows"], 1)
        self.assertEqual(report["blocked_rows"][0]["block_reason"], "missing_anchor_record")

    def test_writer_exports_report_records_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            deferred_path = root / "deferred.csv"
            anchor_path = root / "anchors.jsonl"
            raw_dir = root / "raw"
            quote_path = root / "quote.jsonl"
            output_dir = root / "out"
            raw_dir.mkdir()
            deferred_path.write_text(
                "event_id,wallet_address,token_address,signal_time,needed_snapshot_start,needed_snapshot_end,recommended_next_action\n"
                "EventA,WalletA,MintA,100,100,1000,archival_or_onchain_later_snapshot_recovery\n",
                encoding="utf-8",
            )
            anchor_path.write_text(json.dumps(anchor_record(), sort_keys=True) + "\n", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx(), sort_keys=True) + "\n", encoding="utf-8")
            quote_path.write_text(json.dumps({"timestamp": 99, "price_usd": 1.0}, sort_keys=True) + "\n", encoding="utf-8")

            report = write_candidate_onchain_later_snapshot_recovery(
                deferred_queue_path=deferred_path,
                anchor_records_path=anchor_path,
                raw_transactions_dir=raw_dir,
                quote_price_series_path=quote_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertTrue((output_dir / "candidate_onchain_later_snapshot_recovery_fixed.json").exists())
            self.assertTrue((output_dir / "candidate_onchain_later_snapshot_recovery_records_fixed.jsonl").exists())
            self.assertTrue(
                (output_dir / "candidate_onchain_later_snapshot_recovered_forward_records_fixed.jsonl").exists()
            )
            self.assertTrue(
                (output_dir / "candidate_onchain_later_snapshot_combined_repaired_records_fixed.jsonl").exists()
            )
            self.assertTrue((output_dir / "candidate_onchain_later_snapshot_recovery_blocked_fixed.csv").exists())
            self.assertTrue((output_dir / "candidate_onchain_later_snapshot_recovery_fixed.md").exists())
            saved = json.loads((output_dir / "candidate_onchain_later_snapshot_recovery_fixed.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("Candidate Onchain Later-Snapshot Recovery", (output_dir / "candidate_onchain_later_snapshot_recovery_fixed.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
