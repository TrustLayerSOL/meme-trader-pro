import json
import tempfile
import unittest
from pathlib import Path

from utils.build_forward_context_blocker_reduction import write_forward_context_blocker_reduction
from wallets.forward_context_blocker_reduction import build_forward_context_blocker_reduction


def recommendations():
    return {
        "summary": {"promotions_allowed": 0, "wallet_list_mutations": 0, "auto_trust_mutations": 0},
        "recommendations": [
            {
                "wallet": "NeedsSnapshots",
                "recommendation_action": "FIX_FORWARD_ENTRY_CONTEXT",
                "records": 20,
                "known_15m": 0,
                "runner_15m": 0,
                "flat_15m": 0,
                "blocked_records": 12,
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            },
            {
                "wallet": "NeedsQuote",
                "recommendation_action": "FIX_FORWARD_ENTRY_CONTEXT",
                "records": 30,
                "known_15m": 0,
                "runner_15m": 0,
                "flat_15m": 0,
                "blocked_records": 25,
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            },
            {
                "wallet": "ReviewWallet",
                "recommendation_action": "REVIEW_FORWARD_SIGNAL_MANUALLY",
                "records": 10,
                "known_15m": 5,
                "runner_15m": 1,
                "flat_15m": 4,
                "blocked_records": 1,
            },
        ],
    }


def repair_plan():
    return {
        "summary": {"blocked_rows": 37, "wallet_list_mutations": 0, "auto_trust_mutations": 0},
        "wallets": [
            {
                "wallet": "NeedsSnapshots",
                "blocked_rows": 12,
                "tokens": 9,
                "quote_anchor_repair_rows": 12,
                "quote_anchor_and_snapshot_rows": 2,
                "quote_anchor_without_snapshot_rows": 10,
                "needs_market_snapshot_rows": 0,
                "partial_context_rows": 0,
                "repair_action": "NEEDS_MARKET_CONTEXT_COLLECTION",
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            },
            {
                "wallet": "NeedsQuote",
                "blocked_rows": 25,
                "tokens": 19,
                "quote_anchor_repair_rows": 0,
                "quote_anchor_and_snapshot_rows": 0,
                "quote_anchor_without_snapshot_rows": 0,
                "needs_market_snapshot_rows": 25,
                "partial_context_rows": 0,
                "repair_action": "NEEDS_MARKET_CONTEXT_COLLECTION",
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            },
        ],
    }


def rejected_records():
    rows = []
    for idx in range(10):
        rows.append(
            {
                "wallet": "NeedsSnapshots",
                "token_mint": f"MintS{idx}",
                "block_reason": "missing_later_market_snapshot",
                "has_quote_anchor": True,
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            }
        )
    for idx in range(25):
        rows.append(
            {
                "wallet": "NeedsQuote",
                "token_mint": f"MintQ{idx}",
                "block_reason": "missing_valid_execution_price_quote",
                "has_quote_anchor": False,
                "wallet_list_mutation_allowed": False,
                "can_mutate_wallet_trust": False,
            }
        )
    return rows


class ForwardContextBlockerReductionTests(unittest.TestCase):
    def test_builds_fix_context_only_priority_queue_without_mutations(self):
        report = build_forward_context_blocker_reduction(
            recommendations=recommendations(),
            repair_plan=repair_plan(),
            resolver_report={"summary": {"resolved_rows": 2, "known_15m_outcomes": 1}},
            rejected_records=rejected_records(),
            generated_at=123.0,
            run_id="fixed",
        )

        self.assertEqual(report["mode"], "FORWARD_CONTEXT_BLOCKER_REDUCTION_REVIEW_ONLY")
        self.assertEqual(report["summary"]["fix_context_wallets"], 2)
        self.assertEqual(report["summary"]["promotions_allowed"], 0)
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertEqual([row["wallet_address"] for row in report["wallets"]], ["NeedsSnapshots", "NeedsQuote"])
        self.assertEqual(report["wallets"][0]["recommended_context_action"], "repair_market_snapshot")
        self.assertEqual(report["wallets"][1]["recommended_context_action"], "repair_entry_timestamp")

    def test_writer_persists_json_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recommendations_path = root / "recommendations.json"
            repair_plan_path = root / "repair_plan.json"
            resolver_path = root / "resolver.json"
            rejected_path = root / "rejected.jsonl"
            output_dir = root / "out"
            recommendations_path.write_text(json.dumps(recommendations()), encoding="utf-8")
            repair_plan_path.write_text(json.dumps(repair_plan()), encoding="utf-8")
            resolver_path.write_text(json.dumps({"summary": {"resolved_rows": 2, "known_15m_outcomes": 1}}), encoding="utf-8")
            rejected_path.write_text("\n".join(json.dumps(row) for row in rejected_records()) + "\n", encoding="utf-8")

            report = write_forward_context_blocker_reduction(
                recommendations_path=recommendations_path,
                repair_plan_path=repair_plan_path,
                resolver_report_path=resolver_path,
                rejected_records_path=rejected_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=123.0,
            )

            self.assertTrue((output_dir / "forward_context_blocker_reduction_fixed.json").exists())
            self.assertTrue((output_dir / "forward_context_blocker_reduction_fixed.csv").exists())
            self.assertTrue((output_dir / "forward_context_blocker_reduction_fixed.md").exists())
            self.assertEqual(report["summary"]["fix_context_wallets"], 2)
            self.assertIn("Context Blocker Reduction", (output_dir / "forward_context_blocker_reduction_fixed.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
