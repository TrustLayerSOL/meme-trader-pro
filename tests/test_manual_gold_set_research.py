from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from research.manual_gold_set import (
    CONFIDENCE_TIERS,
    build_manual_research_packet,
    build_proof_readiness_report,
    import_manual_evidence,
    import_solscan_historical_evidence,
    rank_proof_candidates,
)
from wallets.score_ready_market_context import build_score_ready_market_context_report


def score_ready_report() -> dict:
    return {
        "summary": {
            "records_scanned": 3,
            "score_ready_records": 1,
            "near_score_ready_records": 2,
        },
        "records": [
            {
                "wallet": "WalletA",
                "token_mint": "MintA",
                "timestamp": 1710000000,
                "transaction_signature": "SigA",
                "readiness_status": "needs_archival_supply_for_market_cap",
                "next_action": "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT",
                "decision_time_safe": True,
                "price_present": True,
                "liquidity_present": True,
                "price": 0.002,
                "liquidity": 25000,
                "blocked_by": ["market_cap", "missing_archival_supply"],
                "source_status": "onchain_price_liquidity_recovered",
            },
            {
                "wallet": "WalletA",
                "token_mint": "MintB",
                "timestamp": 1710000010,
                "transaction_signature": "SigB",
                "readiness_status": "needs_archival_supply_for_market_cap",
                "next_action": "FETCH_ARCHIVAL_SUPPLY_AT_OR_BEFORE_DECISION_SLOT",
                "decision_time_safe": True,
                "price_present": True,
                "liquidity_present": True,
                "price": 0.003,
                "liquidity": 90000,
                "blocked_by": ["market_cap", "missing_archival_supply"],
                "source_status": "onchain_price_liquidity_recovered",
            },
            {
                "wallet": "WalletC",
                "token_mint": "MintC",
                "timestamp": 1710000020,
                "transaction_signature": "SigC",
                "readiness_status": "blocked_missing_price",
                "next_action": "RECOVER_DECISION_TIME_PRICE",
                "decision_time_safe": True,
                "price_present": False,
                "liquidity_present": True,
                "liquidity": 10000,
            },
        ],
    }


def recovery_plan() -> dict:
    return {
        "candidate_rows": [
            {
                "wallet": "WalletA",
                "token_mint": "MintA",
                "transaction_signature": "SigA",
                "decision_slot": 123,
                "decision_block_time": 1710000000,
                "required_evidence": "historical_mint_account_supply_at_or_before_decision_slot",
            },
            {
                "wallet": "WalletA",
                "token_mint": "MintB",
                "transaction_signature": "SigB",
                "decision_slot": 124,
                "decision_block_time": 1710000010,
                "required_evidence": "historical_mint_account_supply_at_or_before_decision_slot",
            },
        ]
    }


class ManualGoldSetResearchTests(unittest.TestCase):
    def test_rank_proof_candidates_prioritizes_near_ready_rows_with_repeated_wallets(self):
        rows = rank_proof_candidates(score_ready_report(), recovery_plan(), limit=25)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["wallet"], "WalletA")
        self.assertEqual(rows[0]["missing_proof_reason"], "missing_archival_supply")
        self.assertIn("price/liquidity already recovered", rows[0]["why_high_priority"])
        self.assertIn("solscan.io/token", rows[0]["solscan_token_link"])
        self.assertGreaterEqual(rows[0]["priority_score"], rows[1]["priority_score"])

    def test_export_packet_writes_csv_json_and_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            result = build_manual_research_packet(
                score_ready_report(),
                recovery_plan(),
                output_dir=out_dir,
                limit=25,
            )

            self.assertTrue((out_dir / "manual_research_packet.csv").exists())
            self.assertTrue((out_dir / "manual_research_packet.json").exists())
            self.assertTrue((out_dir / "manual_evidence_template.csv").exists())
            packet = json.loads((out_dir / "manual_research_packet.json").read_text())
            self.assertEqual(packet["summary"]["candidates_exported"], 2)
            with (out_dir / "manual_evidence_template.csv").open() as handle:
                header = next(csv.reader(handle))
            self.assertEqual(header, result["template_columns"])

    def test_import_manual_evidence_rejects_invalid_rows_and_preserves_tier_a_supply_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "manual_evidence.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "candidate_id",
                        "mint",
                        "decision_slot",
                        "decision_timestamp",
                        "verified_supply",
                        "verified_market_cap",
                        "evidence_source",
                        "evidence_url",
                        "screenshot_path",
                        "confidence_tier",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "candidate_id": "manual_MintA_123_SigA",
                        "mint": "MintA",
                        "decision_slot": "123",
                        "decision_timestamp": "1710000000",
                        "verified_supply": "1000000",
                        "verified_market_cap": "2000",
                        "evidence_source": "Solscan historical page",
                        "evidence_url": "https://solscan.io/token/MintA",
                        "confidence_tier": "A_FULL_REPLAY_SAFE",
                        "notes": "Supply visible for slot at or before decision.",
                    }
                )
                writer.writerow(
                    {
                        "candidate_id": "manual_MintB_124_SigB",
                        "mint": "MintB",
                        "decision_slot": "124",
                        "decision_timestamp": "1710000010",
                        "verified_supply": "0",
                        "verified_market_cap": "2000",
                        "evidence_source": "Solscan",
                        "evidence_url": "https://solscan.io/token/MintB",
                        "confidence_tier": "A_FULL_REPLAY_SAFE",
                        "notes": "Bad supply.",
                    }
                )

            result = import_manual_evidence(
                csv_path,
                score_ready_report=score_ready_report(),
                recovery_plan=recovery_plan(),
                output_dir=tmp_path,
            )

            self.assertEqual(result["summary"]["accepted_rows"], 1)
            self.assertEqual(result["summary"]["rejected_rows"], 1)
            records = [
                json.loads(line)
                for line in (tmp_path / "manual_supply_evidence_records.jsonl").read_text().splitlines()
            ]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "archival_supply_recovered")
            self.assertEqual(records[0]["source"], "manual_gold_set")
            self.assertTrue(records[0]["decision_time_safe"])

    def test_import_manual_evidence_accepts_partial_market_cap_without_supply_without_unblocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "manual_evidence.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "candidate_id",
                        "mint",
                        "decision_slot",
                        "decision_timestamp",
                        "verified_supply",
                        "verified_market_cap",
                        "evidence_source",
                        "evidence_url",
                        "screenshot_path",
                        "confidence_tier",
                        "notes",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "candidate_id": "manual_MintA_123_SigA",
                        "mint": "MintA",
                        "decision_slot": "123",
                        "decision_timestamp": "1710000000",
                        "verified_supply": "",
                        "verified_market_cap": "4700000",
                        "evidence_source": "Dexscreener 1s historical MCap chart",
                        "evidence_url": "https://dexscreener.com/solana/MintA",
                        "confidence_tier": "B_STRONG_PARTIAL",
                        "notes": "Historical chart was positioned at the candidate decision timestamp, but no supply proof was captured.",
                    }
                )

            result = import_manual_evidence(
                csv_path,
                score_ready_report=score_ready_report(),
                recovery_plan=recovery_plan(),
                output_dir=tmp_path,
            )

            self.assertEqual(result["summary"]["accepted_rows"], 1)
            self.assertEqual(result["summary"]["manual_tier_a_supply_records"], 0)
            records = [
                json.loads(line)
                for line in (tmp_path / "manual_evidence_imported.jsonl").read_text().splitlines()
            ]
            self.assertEqual(records[0]["confidence_tier"], "B_STRONG_PARTIAL")
            self.assertFalse(records[0]["proof_unblock_allowed"])
            self.assertFalse((tmp_path / "manual_supply_evidence_records.jsonl").read_text().strip())

    def test_import_solscan_historical_evidence_stores_matching_rows_as_partial_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "solscan_export.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["Signature", "Time", "Action", "Amount", "Value", "Program"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Signature": "SigA",
                        "Time": "2024-03-09 16:00:00",
                        "Action": "SWAP",
                        "Amount": "1000 MintA",
                        "Value": "$2,000.00",
                        "Program": "Pump.fun AMM",
                    }
                )

            result = import_solscan_historical_evidence(
                csv_path,
                candidate_id="manual_MintA_123_SigA",
                source_url="https://solscan.io/token/MintA#activities",
                score_ready_report=score_ready_report(),
                recovery_plan=recovery_plan(),
                output_dir=tmp_path,
            )

            self.assertEqual(result["summary"]["accepted_rows"], 1)
            self.assertEqual(result["summary"]["rejected_rows"], 0)
            rows = [
                json.loads(line)
                for line in (tmp_path / "solscan_historical_evidence_imported.jsonl").read_text().splitlines()
            ]
            self.assertEqual(rows[0]["candidate_id"], "manual_MintA_123_SigA")
            self.assertEqual(rows[0]["confidence_tier"], "B_STRONG_PARTIAL")
            self.assertFalse(rows[0]["proof_unblock_allowed"])
            self.assertIn("Solscan historical", rows[0]["evidence_source"])

    def test_import_solscan_historical_evidence_accepts_current_solscan_defi_export_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "solscan_defi_export.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "Signature",
                        "Block Time",
                        "Human Time",
                        "Action",
                        "From",
                        "Token1",
                        "Amount1",
                        "TokenDecimals1",
                        "Token2",
                        "Amount2",
                        "TokenDecimals2",
                        "Value",
                        "Programs",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Signature": "SigA",
                        "Block Time": "1710000000",
                        "Human Time": "2024-03-09T16:00:00.000Z",
                        "Action": "ACTIVITY_TOKEN_SWAP",
                        "From": "TraderA",
                        "Token1": "So11111111111111111111111111111111111111112",
                        "Amount1": "1000000000",
                        "TokenDecimals1": "9",
                        "Token2": "MintA",
                        "Amount2": "123450000",
                        "TokenDecimals2": "6",
                        "Value": "2000",
                        "Programs": "PumpProgram|Router",
                    }
                )

            result = import_solscan_historical_evidence(
                csv_path,
                candidate_id="manual_MintA_123_SigA",
                source_url="https://solscan.io/token/MintA#activities",
                score_ready_report=score_ready_report(),
                recovery_plan=recovery_plan(),
                output_dir=tmp_path,
            )

            self.assertEqual(result["summary"]["accepted_rows"], 1)
            self.assertEqual(result["summary"]["rejected_rows"], 0)
            rows = [
                json.loads(line)
                for line in (tmp_path / "solscan_historical_evidence_imported.jsonl").read_text().splitlines()
            ]
            self.assertEqual(rows[0]["amount"], "123.45 MintA")
            self.assertEqual(rows[0]["observed_time"], "2024-03-09T16:00:00.000Z")
            self.assertEqual(rows[0]["program"], "PumpProgram|Router")
            self.assertEqual(rows[0]["solscan_from"], "TraderA")
            self.assertFalse(rows[0]["proof_unblock_allowed"])

    def test_import_manual_evidence_never_overwrites_stronger_evidence_with_weaker(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            existing = {
                "candidate_id": "manual_MintA_123_SigA",
                "mint": "MintA",
                "confidence_tier": "A_FULL_REPLAY_SAFE",
                "verified_supply": 1000000,
                "verified_market_cap": 2000,
                "evidence_source": "Solscan",
                "evidence_url": "https://solscan.io/token/MintA",
                "notes": "Existing strong evidence.",
            }
            (tmp_path / "manual_evidence_imported.jsonl").write_text(json.dumps(existing) + "\n")
            csv_path = tmp_path / "manual_evidence.csv"
            with csv_path.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(existing.keys()) + ["decision_slot", "decision_timestamp"])
                writer.writeheader()
                writer.writerow(
                    {
                        **existing,
                        "confidence_tier": "C_SUGGESTIVE",
                        "verified_supply": "2000000",
                        "decision_slot": "123",
                        "decision_timestamp": "1710000000",
                        "notes": "Weaker evidence should not replace A.",
                    }
                )

            result = import_manual_evidence(
                csv_path,
                score_ready_report=score_ready_report(),
                recovery_plan=recovery_plan(),
                output_dir=tmp_path,
            )

            self.assertEqual(result["summary"]["accepted_rows"], 0)
            self.assertEqual(result["summary"]["preserved_stronger_rows"], 1)
            stored = json.loads((tmp_path / "manual_evidence_imported.jsonl").read_text().strip())
            self.assertEqual(stored["confidence_tier"], "A_FULL_REPLAY_SAFE")
            self.assertEqual(stored["verified_supply"], 1000000)

    def test_proof_readiness_report_counts_manual_tiers_without_overclaiming(self):
        report = build_proof_readiness_report(
            score_ready_report=score_ready_report(),
            stage8_report={"summary": {"proof_readiness_pct": 11}},
            manual_evidence_rows=[
                {"candidate_id": "a", "confidence_tier": "A_FULL_REPLAY_SAFE", "proof_unblock_allowed": True},
                {"candidate_id": "b", "confidence_tier": "B_STRONG_PARTIAL", "proof_unblock_allowed": False},
            ],
        )

        self.assertEqual(report["summary"]["manual_tier_a_rows"], 1)
        self.assertEqual(report["summary"]["manual_tier_b_rows"], 1)
        self.assertEqual(report["summary"]["manual_unblocked_rows"], 1)
        self.assertGreaterEqual(report["summary"]["manual_adjusted_proof_readiness_pct"], 11)
        self.assertEqual(CONFIDENCE_TIERS[0], "A_FULL_REPLAY_SAFE")

    def test_tier_a_manual_supply_can_make_matching_context_score_ready(self):
        report = build_score_ready_market_context_report(
            onchain_market_context_records=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "transaction_signature": "SigA",
                    "status": "onchain_price_liquidity_recovered",
                    "block_reasons": ["blocked_missing_market_cap", "blocked_missing_supply"],
                    "decision_time_context": {
                        "decision_time_safe": True,
                        "timestamp": 1710000000,
                        "price": 0.002,
                        "liquidity": 25000,
                    },
                }
            ],
            supply_evidence_records=[],
            archival_supply_records=[],
            manual_supply_records=[
                {
                    "wallet": "WalletA",
                    "token_mint": "MintA",
                    "transaction_signature": "SigA",
                    "status": "archival_supply_recovered",
                    "source": "manual_gold_set",
                    "decision_time_safe": True,
                    "ui_supply": 1000000,
                }
            ],
        )

        self.assertEqual(report["summary"]["score_ready_records"], 1)
        self.assertEqual(report["records"][0]["supply_source"], "manual_gold_set")
        self.assertEqual(report["records"][0]["market_cap"], 2000)


if __name__ == "__main__":
    unittest.main()
