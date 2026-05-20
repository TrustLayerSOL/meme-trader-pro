import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.build_score_ready_market_context import write_score_ready_market_context_report
from wallets.score_ready_market_context import build_score_ready_market_context_report


def onchain_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "score_ready_candidate": False,
        "status": "onchain_price_liquidity_recovered",
        "decision_time_context": {
            "decision_time_safe": True,
            "price": 0.01,
            "liquidity": 10_000,
            "market_cap": None,
        },
        "block_reasons": ["blocked_missing_market_cap", "blocked_missing_supply"],
        "missing_fields": ["market_cap"],
    }
    row.update(overrides)
    return row


def supply_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "status": "needs_archival_supply",
        "decision_time_safe": False,
        "ui_supply": None,
        "decimals": 6,
        "block_reasons": ["blocked_missing_supply"],
    }
    row.update(overrides)
    return row


def archival_supply_row(**overrides):
    row = {
        "wallet": "WalletA",
        "token_mint": "MintA",
        "timestamp": 1000,
        "transaction_signature": "SigA",
        "status": "archival_supply_recovered",
        "decision_time_safe": True,
        "ui_supply": 1_000_000,
        "raw_supply": "1000000000000",
        "decimals": 6,
        "snapshot_slot": 90,
        "decision_slot": 100,
        "block_reasons": [],
    }
    row.update(overrides)
    return row


class ScoreReadyMarketContextTests(unittest.TestCase):
    def test_classifies_price_liquidity_rows_as_archival_supply_candidates(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[onchain_row()],
            supply_evidence_records=[supply_row()],
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertEqual(report["summary"]["score_ready_records"], 0)
        self.assertEqual(report["summary"]["archival_supply_candidate_rows"], 1)
        self.assertEqual(report["summary"]["tokens_needing_archival_supply"], 1)
        self.assertEqual(report["summary"]["rows_with_price_and_liquidity"], 1)
        self.assertEqual(report["records"][0]["readiness_status"], "needs_archival_supply_for_market_cap")
        self.assertEqual(report["records"][0]["next_action"], "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT")
        self.assertIn("missing_archival_supply", report["records"][0]["blocked_by"])

    def test_marks_rows_score_ready_only_when_decision_time_market_cap_exists(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[
                onchain_row(
                    score_ready_candidate=True,
                    decision_time_context={
                        "decision_time_safe": True,
                        "price": 0.01,
                        "liquidity": 10_000,
                        "market_cap": 10_000_000,
                        "token_supply": 1_000_000_000,
                    },
                    block_reasons=[],
                    missing_fields=[],
                )
            ],
            supply_evidence_records=[
                supply_row(
                    status="supply_recovered",
                    decision_time_safe=True,
                    ui_supply=1_000_000_000,
                    block_reasons=[],
                )
            ],
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["score_ready_records"], 1)
        self.assertEqual(report["records"][0]["readiness_status"], "score_ready")
        self.assertTrue(report["records"][0]["decision_time_safe"])
        self.assertFalse(report["records"][0]["can_mutate_wallet_trust"])

    def test_archival_supply_recomputes_market_cap_and_marks_row_score_ready(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[onchain_row()],
            supply_evidence_records=[supply_row()],
            archival_supply_records=[archival_supply_row()],
            generated_at=123.0,
        )

        record = report["records"][0]
        self.assertEqual(report["summary"]["score_ready_records"], 1)
        self.assertEqual(report["summary"]["needs_market_cap_recompute_rows"], 0)
        self.assertEqual(record["readiness_status"], "score_ready")
        self.assertEqual(record["next_action"], "NO_ACTION_SCORE_READY")
        self.assertEqual(record["supply_status"], "archival_supply_recovered")
        self.assertEqual(record["token_supply"], 1_000_000)
        self.assertEqual(record["market_cap"], 10_000)
        self.assertTrue(record["supply_decision_time_safe"])
        self.assertEqual(record["supply_source"], "archival_supply_evidence")

    def test_tier_a_manual_market_cap_applies_to_same_mint_and_timestamp_group(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[
                onchain_row(
                    wallet="WalletB",
                    transaction_signature="SigB",
                    decision_time_context={
                        "decision_time_safe": True,
                        "timestamp": 1000,
                        "price": 0.01,
                        "liquidity": 10_000,
                    },
                )
            ],
            supply_evidence_records=[],
            manual_market_cap_records=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "transaction_signature": "SigA",
                    "decision_timestamp": 1000,
                    "confidence_tier": "A_FULL_REPLAY_SAFE",
                    "proof_unblock_allowed": True,
                    "decision_time_safe": True,
                    "verified_market_cap": 4_700_000,
                    "evidence_source": "Dexscreener 1s historical MCap chart",
                }
            ],
            generated_at=123.0,
        )

        record = report["records"][0]
        self.assertEqual(record["readiness_status"], "score_ready")
        self.assertEqual(record["market_cap"], 4_700_000)
        self.assertEqual(record["market_cap_source"], "manual_gold_set_market_cap_group")

    def test_prior_decision_time_market_snapshot_does_not_require_supply_evidence(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[
                onchain_row(
                    score_ready_candidate=True,
                    decision_time_context={
                        "decision_time_safe": True,
                        "price": 0.01,
                        "liquidity": 10_000,
                        "market_cap": 2_500_000,
                        "market_cap_source": "prior_decision_time_market_snapshot",
                        "market_cap_snapshot_time": 900,
                    },
                    block_reasons=[],
                    missing_fields=[],
                )
            ],
            supply_evidence_records=[supply_row(status="needs_archival_supply", decision_time_safe=False)],
            generated_at=123.0,
        )

        record = report["records"][0]
        self.assertEqual(record["readiness_status"], "score_ready")
        self.assertEqual(record["next_action"], "NO_ACTION_SCORE_READY")
        self.assertEqual(report["summary"]["score_ready_records"], 1)

    def test_keeps_missing_price_or_liquidity_rows_blocked(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[
                onchain_row(
                    token_mint="MintNoPrice",
                    transaction_signature="SigNoPrice",
                    decision_time_context={"decision_time_safe": True, "liquidity": 10_000, "market_cap": None},
                    block_reasons=["blocked_missing_price"],
                ),
                onchain_row(
                    token_mint="MintNoLiquidity",
                    transaction_signature="SigNoLiquidity",
                    decision_time_context={"decision_time_safe": True, "price": 0.01, "market_cap": None},
                    block_reasons=["blocked_missing_liquidity"],
                ),
            ],
            supply_evidence_records=[],
            generated_at=123.0,
        )

        statuses = {row["token_mint"]: row["readiness_status"] for row in report["records"]}
        self.assertEqual(statuses["MintNoPrice"], "blocked_missing_price")
        self.assertEqual(statuses["MintNoLiquidity"], "blocked_missing_liquidity")
        self.assertEqual(report["summary"]["blocked_missing_price_rows"], 1)
        self.assertEqual(report["summary"]["blocked_missing_liquidity_rows"], 1)

    def test_writer_creates_report_and_records(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            onchain_path = root / "onchain.jsonl"
            supply_path = root / "supply.jsonl"
            report_path = root / "score_ready_market_context_report.json"
            records_path = root / "score_ready_market_context_records.jsonl"
            onchain_path.write_text(json.dumps(onchain_row()) + "\n", encoding="utf-8")
            supply_path.write_text(json.dumps(supply_row()) + "\n", encoding="utf-8")

            report = write_score_ready_market_context_report(
                onchain_records_path=onchain_path,
                supply_records_path=supply_path,
                archival_supply_records_path=root / "missing_archival.jsonl",
                report_path=report_path,
                output_records_path=records_path,
                generated_at=123.0,
            )

            self.assertTrue(report_path.exists())
            self.assertTrue(records_path.exists())
            self.assertEqual(report["summary"]["records_scanned"], 1)
            saved = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "SCORE_READY_MARKET_CONTEXT_REVIEW_ONLY")


if __name__ == "__main__":
    unittest.main()
