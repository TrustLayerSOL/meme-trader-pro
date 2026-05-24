import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_wallet_trust_review_packet import build_obsidian_pages
from utils.build_forward_wallet_trust_review_packet import write_forward_wallet_trust_review_packet
from wallets.forward_wallet_trust_review_packet import TOP_WALLET
from wallets.forward_wallet_trust_review_packet import build_forward_wallet_trust_review_packet


def record(wallet: str, event: str, outcome: str = "flat", *, blocked: bool = False, token: str | None = None):
    row = {
        "event_id": event,
        "wallet": wallet,
        "token_mint": token or f"Mint{event}",
        "token_symbol": f"T{event}",
        "signal_time": 1000.0 + len(event),
        "transaction_signature": f"sig-{event}",
        "observed_action": "buy",
        "outcome_window_labels": {"15m": {"outcome_type": outcome, "pnl_pct": 12.5 if outcome == "runner" else 0.2}},
        "decision_context": {
            "estimated_entry_context": {
                "snapshot_time": 1000.0,
                "price": 0.01,
                "liquidity": 25000,
                "market_cap": 100000,
                "snapshot_lag_seconds": 20,
            }
        },
        "status": "resolved",
    }
    if blocked:
        row["status"] = "blocked_missing_forward_entry_context"
        row["block_reasons"] = ["missing_forward_entry_context"]
        row["decision_context"] = {}
        row["outcome_window_labels"] = {"15m": {"outcome_type": "unknown"}}
    return row


def recommendation(wallet: str, action: str, *, known: int = 2, runner: int = 1, flat: int = 1, blocked: int = 0):
    return {
        "wallet": wallet,
        "recommendation_action": action,
        "known_15m": known,
        "runner_15m": runner,
        "flat_15m": flat,
        "loser_15m": 0,
        "blocked_records": blocked,
        "auto_apply": False,
        "wallet_list_mutation_allowed": False,
    }


def score_row(wallet: str, *, records: int, known: int, runner: int, flat: int, blocked: int):
    return {
        "wallet": wallet,
        "records": records,
        "known_15m": known,
        "runner_15m": runner,
        "flat_15m": flat,
        "loser_15m": 0,
        "blocked_records": blocked,
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def fixtures():
    wallet_b = "WalletB"
    wallet_c = "WalletC"
    blocked_wallet = "BlockedWallet"
    flat_wallet = "FlatWallet"
    records = []
    for idx in range(25):
        outcome = "runner" if idx in {0, 1} else "flat"
        records.append(record(TOP_WALLET, f"top-{idx}", outcome, token=f"TopMint{idx}"))
    records.append(record(TOP_WALLET, "top-blocked", blocked=True, token="TopBlocked"))
    records.extend(
        [
            record(wallet_b, "b-1", "runner"),
            record(wallet_b, "b-2", "flat"),
            record(wallet_c, "c-1", "runner"),
            record(wallet_c, "c-2", "flat"),
            record(flat_wallet, "flat-1", "flat"),
            record(flat_wallet, "flat-2", "flat"),
            record(blocked_wallet, "blocked-1", blocked=True),
            record(blocked_wallet, "blocked-2", blocked=True),
        ]
    )
    recommendations = {
        "summary": {"promotions_allowed": 0, "wallet_list_mutations": 0, "auto_trust_mutations": 0},
        "recommendations": [
            recommendation(TOP_WALLET, "REVIEW_FORWARD_SIGNAL_MANUALLY", known=25, runner=2, flat=23, blocked=1),
            recommendation(wallet_b, "REVIEW_FORWARD_SIGNAL_MANUALLY"),
            recommendation(wallet_c, "REVIEW_FORWARD_SIGNAL_MANUALLY"),
            recommendation(flat_wallet, "HOLD_NO_PROMOTION_FLAT_ONLY", known=2, runner=0, flat=2),
            recommendation(blocked_wallet, "FIX_FORWARD_ENTRY_CONTEXT", known=0, runner=0, flat=0, blocked=2),
        ],
    }
    merged_scorecard = {
        "scorecard": {
            "wallets": [
                score_row(TOP_WALLET, records=26, known=25, runner=2, flat=23, blocked=1),
                score_row(wallet_b, records=2, known=2, runner=1, flat=1, blocked=0),
                score_row(wallet_c, records=2, known=2, runner=1, flat=1, blocked=0),
                score_row(flat_wallet, records=2, known=2, runner=0, flat=2, blocked=0),
                score_row(blocked_wallet, records=2, known=0, runner=0, flat=0, blocked=2),
            ]
        }
    }
    canaries = [
        {
            "limits": {"cycle_interval_seconds": 300},
            "budget": {"projected_rpc_calls_per_day": 8640, "max_rpc_calls_per_day": 120000},
            "summary": {"wallets_processed": 10, "evidence_rows_created": 5, "market_snapshots_collected": 4},
            "blockers": ["high_rpc_error_rate"],
            "provider_status_counts": {"healthy": 1},
        }
    ]
    safety = {"overall": "PAPER_SAFE", "live_allowed": False, "live_enabled": False, "paper_enabled": True}
    return records, merged_scorecard, recommendations, canaries, safety


class ForwardWalletTrustReviewPacketTests(unittest.TestCase):
    def test_packet_filters_review_bucket_and_keeps_mutations_disabled(self):
        records, scorecard, recommendations, canaries, safety = fixtures()
        report = build_forward_wallet_trust_review_packet(
            original_records=records,
            repaired_records=[],
            merged_scorecard=scorecard,
            recommendations=recommendations,
            canary_reports=canaries,
            safety_report=safety,
            run_id="fixed",
            generated_at=123.0,
        )

        self.assertEqual([row["recommendation_bucket"] for row in report["wallets"]], ["review_behavioral_signal"] * 3)
        self.assertEqual(report["summary"]["review_wallets"], 3)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertTrue(all(row["promotion_allowed"] is False for row in report["wallets"]))

    def test_distribution_context_gap_and_top_wallet_case_study(self):
        records, scorecard, recommendations, canaries, safety = fixtures()
        report = build_forward_wallet_trust_review_packet(
            original_records=records,
            repaired_records=[],
            merged_scorecard=scorecard,
            recommendations=recommendations,
            canary_reports=canaries,
            safety_report=safety,
            run_id="fixed",
            generated_at=123.0,
        )
        top = next(row for row in report["wallets"] if row["wallet_address"] == TOP_WALLET)

        self.assertEqual(top["runner_15m_count"], 2)
        self.assertEqual(top["flat_15m_count"], 23)
        self.assertEqual(top["blocked_record_count"], 1)
        self.assertLess(top["context_completion_rate"], 1.0)
        self.assertEqual(report["context_gap_analysis"]["top_context_blocked_wallets"][0]["wallet_address"], "BlockedWallet")
        self.assertLessEqual(
            report["context_gap_analysis"]["repairable_blocked_count"],
            report["context_gap_analysis"]["total_blocked_records"],
        )
        self.assertIn("not_trusted", report["top_wallet_case_study"]["current_conclusion"])
        self.assertIn("no_promotion_allowed", report["top_wallet_case_study"]["current_conclusion"])

    def test_safety_and_rpc_health_statuses_are_explicit(self):
        records, scorecard, recommendations, canaries, safety = fixtures()
        report = build_forward_wallet_trust_review_packet(
            original_records=records,
            repaired_records=[],
            merged_scorecard=scorecard,
            recommendations=recommendations,
            canary_reports=canaries,
            safety_report=safety,
            run_id="fixed",
            generated_at=123.0,
        )
        self.assertEqual(report["safety_lock_verification"]["safety_status"], "locked_safe")
        self.assertEqual(report["rpc_collection_health"]["status"], "healthy_but_interval_mismatch")

        unsafe = dict(safety, live_enabled=True)
        unsafe_report = build_forward_wallet_trust_review_packet(
            original_records=records,
            repaired_records=[],
            merged_scorecard=scorecard,
            recommendations=recommendations,
            canary_reports=canaries,
            safety_report=unsafe,
            run_id="fixed",
            generated_at=123.0,
        )
        self.assertEqual(unsafe_report["safety_lock_verification"]["safety_status"], "unsafe_block_run")
        self.assertTrue(all(row["review_status"] == "manual_review_required" for row in unsafe_report["wallets"]))

    def test_obsidian_pages_include_required_explanatory_headers_and_guardrails(self):
        records, scorecard, recommendations, canaries, safety = fixtures()
        report = build_forward_wallet_trust_review_packet(
            original_records=records,
            repaired_records=[],
            merged_scorecard=scorecard,
            recommendations=recommendations,
            canary_reports=canaries,
            safety_report=safety,
            run_id="fixed",
            generated_at=123.0,
        )
        pages = build_obsidian_pages(report)

        self.assertEqual(len(pages), 8)
        for _, body in pages.values():
            self.assertIn("## What This Page Does", body)
        guardrails = pages["Dashboards/Research Guardrails.md"][1]
        self.assertIn("No live trading", guardrails)
        self.assertIn("No execution", guardrails)
        self.assertIn("No auto-promotion", guardrails)

    def test_writer_exports_deterministic_review_files(self):
        records, scorecard, recommendations, canaries, safety = fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            scorecard_path = root / "scorecard.json"
            recommendations_path = root / "recommendations.json"
            canary_dir = root / "canaries"
            output_dir = root / "output"
            canary_dir.mkdir()
            records_path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in records) + "\n", encoding="utf-8")
            scorecard_path.write_text(json.dumps(scorecard, sort_keys=True), encoding="utf-8")
            recommendations_path.write_text(json.dumps(recommendations, sort_keys=True), encoding="utf-8")
            (canary_dir / "forward_free_rpc_canary_001.json").write_text(json.dumps(canaries[0], sort_keys=True), encoding="utf-8")

            report = write_forward_wallet_trust_review_packet(
                records_path=records_path,
                repaired_records_path=root / "missing_repaired.jsonl",
                merged_scorecard_path=scorecard_path,
                recommendations_path=recommendations_path,
                resolver_report_path=root / "missing_resolver.json",
                canary_dir=canary_dir,
                output_dir=output_dir,
                obsidian_vault=None,
                run_id="fixed-run",
                generated_at=123.0,
            )

            expected = output_dir / "forward_wallet_trust_review_packet_fixed-run.json"
            self.assertTrue(expected.exists())
            self.assertTrue((output_dir / "forward_wallet_trust_review_packet_fixed-run.csv").exists())
            self.assertTrue((output_dir / "wallet_event_evidence_fixed-run.csv").exists())
            saved = json.loads(expected.read_text(encoding="utf-8"))
            self.assertEqual(saved["run_id"], "fixed-run")
            self.assertEqual(saved["generated_at"], 123.0)
            self.assertEqual(saved["summary"], report["summary"])


if __name__ == "__main__":
    unittest.main()
