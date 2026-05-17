import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_archival_supply_recovery_plan import write_archival_supply_recovery_plan
from wallets.archival_supply_recovery_plan import build_archival_supply_recovery_plan


def score_ready_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "readiness_status": "needs_archival_supply_for_market_cap",
        "next_action": "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT",
        "decision_time_safe": True,
        "price_present": True,
        "liquidity_present": True,
        "market_cap_present": False,
        "supply_present": False,
        "decimals": 6,
        "blocked_by": ["missing_archival_supply", "market_cap"],
    }
    row.update(overrides)
    return row


def raw_tx(signature="SigA", slot=12345, block_time=1000):
    return {
        "signature": signature,
        "source_file": "data/wallet_backfills/raw_transactions/raw.jsonl",
        "transaction": {
            "slot": slot,
            "blockTime": block_time,
            "transaction": {"signatures": [signature]},
            "meta": {"preTokenBalances": [], "postTokenBalances": []},
        },
    }


class ArchivalSupplyRecoveryPlanTests(unittest.TestCase):
    def test_groups_archival_supply_requirements_by_token_and_decision_slot(self):
        report = build_archival_supply_recovery_plan(
            score_ready_market_context_records=[
                score_ready_row(wallet="WalletA", token_mint="MintA", transaction_signature="SigA", timestamp=1000),
                score_ready_row(wallet="WalletB", token_mint="MintA", transaction_signature="SigB", timestamp=1050),
                score_ready_row(wallet="WalletC", token_mint="MintB", transaction_signature="SigC", timestamp=1100, decimals=9),
            ],
            raw_transactions=[
                raw_tx("SigA", slot=12345, block_time=1000),
                raw_tx("SigB", slot=12390, block_time=1050),
                raw_tx("SigC", slot=13000, block_time=1100),
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertEqual(report["summary"]["plan_completion_pct"], 100)
        self.assertEqual(report["summary"]["candidate_rows"], 3)
        self.assertEqual(report["summary"]["tokens_to_fetch"], 2)
        self.assertEqual(report["summary"]["rows_with_decision_slot"], 3)
        self.assertEqual(report["summary"]["rows_missing_decision_slot"], 0)
        self.assertEqual(report["token_requirements"][0]["token_mint"], "MintA")
        self.assertEqual(report["token_requirements"][0]["earliest_decision_slot"], 12345)
        self.assertEqual(report["token_requirements"][0]["latest_decision_slot"], 12390)
        self.assertEqual(report["token_requirements"][0]["row_count"], 2)
        self.assertEqual(report["token_requirements"][0]["wallet_count"], 2)
        self.assertEqual(report["token_requirements"][0]["status"], "ready_for_archival_supply_fetch")
        self.assertEqual(report["token_requirements"][0]["required_evidence"], "historical_mint_account_supply_at_or_before_decision_slot")
        self.assertFalse(report["token_requirements"][0]["can_mutate_wallet_trust"])

    def test_blocks_rows_without_decision_slot(self):
        report = build_archival_supply_recovery_plan(
            score_ready_market_context_records=[score_ready_row(transaction_signature="MissingSig")],
            raw_transactions=[],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["tokens_to_fetch"], 0)
        self.assertEqual(report["summary"]["tokens_blocked_missing_slot"], 1)
        self.assertEqual(report["token_requirements"][0]["status"], "blocked_missing_decision_slot")
        self.assertIn("missing_raw_transaction_slot", report["token_requirements"][0]["blocked_by"])

    def test_excludes_non_archival_supply_rows(self):
        report = build_archival_supply_recovery_plan(
            score_ready_market_context_records=[
                score_ready_row(token_mint="MintA", transaction_signature="SigA"),
                score_ready_row(
                    token_mint="MintIgnored",
                    transaction_signature="SigIgnored",
                    readiness_status="blocked_missing_price",
                    next_action="RECOVER_DECISION_TIME_PRICE",
                ),
            ],
            raw_transactions=[raw_tx("SigA", slot=1), raw_tx("SigIgnored", slot=2)],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["candidate_rows"], 1)
        self.assertEqual(len(report["token_requirements"]), 1)
        self.assertEqual(report["token_requirements"][0]["token_mint"], "MintA")

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            score_path = root / "score_ready_records.jsonl"
            raw_dir = root / "raw"
            report_path = root / "archival_supply_recovery_plan.json"
            raw_dir.mkdir()
            score_path.write_text(json.dumps(score_ready_row()) + "\n", encoding="utf-8")
            (raw_dir / "raw.jsonl").write_text(json.dumps(raw_tx()) + "\n", encoding="utf-8")

            report = write_archival_supply_recovery_plan(
                score_ready_records_path=score_path,
                raw_transactions_dir=raw_dir,
                report_path=report_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertEqual(report["summary"]["candidate_rows"], 1)
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "ARCHIVAL_SUPPLY_RECOVERY_PLAN_REVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
