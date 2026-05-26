import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_feasibility_probe import write_dune_candidate_feasibility_probe
from wallets.candidate_walk_forward_validation import DEFAULT_CANDIDATE_WALLETS
from wallets.dune_candidate_feasibility import (
    build_dune_candidate_feasibility_report,
    build_dune_sql_queries,
)


class DuneCandidateFeasibilityTests(unittest.TestCase):
    def test_sql_queries_are_candidate_only_and_partition_filtered(self):
        queries = build_dune_sql_queries(
            candidate_wallets=DEFAULT_CANDIDATE_WALLETS[:2],
            start_date="2026-04-01",
            end_date="2026-05-01",
            limit=25,
        )

        self.assertEqual(
            sorted(queries),
            [
                "candidate_dex_trades",
                "candidate_price_coverage",
                "candidate_token_transfers",
                "candidate_transactions",
            ],
        )
        for sql in queries.values():
            self.assertIn("2026-04-01", sql)
            self.assertIn("2026-05-01", sql)
            self.assertIn("LIMIT 25", sql)
            self.assertIn(DEFAULT_CANDIDATE_WALLETS[0], sql)
            self.assertIn(DEFAULT_CANDIDATE_WALLETS[1], sql)
            self.assertNotIn("OtherWallet", sql)

    def test_report_keeps_dune_as_review_only_evidence_layer(self):
        report = build_dune_candidate_feasibility_report(
            candidate_wallets=DEFAULT_CANDIDATE_WALLETS[:2],
            start_date="2026-04-01",
            end_date="2026-05-01",
            query_results={
                "candidate_transactions": [
                    {"wallet_address": DEFAULT_CANDIDATE_WALLETS[0], "tx_count": 3},
                    {"wallet_address": DEFAULT_CANDIDATE_WALLETS[1], "tx_count": 1},
                ],
                "candidate_dex_trades": [
                    {
                        "wallet_address": DEFAULT_CANDIDATE_WALLETS[0],
                        "token_mint": "MintA",
                        "tx_hash": "SigA",
                        "amount_usd": 42.0,
                        "price_usd": 0.01,
                    }
                ],
                "candidate_token_transfers": [
                    {"wallet_address": DEFAULT_CANDIDATE_WALLETS[0], "token_mint": "MintA", "transfer_count": 2}
                ],
                "candidate_price_coverage": [{"token_mint": "MintA", "minute_price_points": 4}],
            },
            generated_at=1000.0,
            execution_mode="mocked",
        )

        summary = report["summary"]
        self.assertEqual(summary["candidate_wallets"], 2)
        self.assertEqual(summary["wallets_with_transaction_history"], 2)
        self.assertEqual(summary["wallets_with_dex_matches"], 1)
        self.assertEqual(summary["quote_anchor_candidate_rows"], 1)
        self.assertEqual(summary["price_context_candidate_rows"], 1)
        self.assertEqual(summary["liquidity_context_candidate_rows"], 0)
        self.assertEqual(summary["market_cap_context_candidate_rows"], 0)
        self.assertEqual(summary["proof_ready_rows"], 0)
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])
        self.assertFalse(report["promotion_allowed"])
        self.assertIn("dune_does_not_fully_solve_liquidity_or_market_cap", report["limitations"])

    def test_writer_exports_json_csv_markdown_and_sql_without_api_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            report = write_dune_candidate_feasibility_probe(
                output_dir=output_dir,
                run_id="fixed",
                candidate_wallets=DEFAULT_CANDIDATE_WALLETS[:1],
                start_date="2026-04-01",
                end_date="2026-05-01",
                execute=False,
                generated_at=1000.0,
            )

            json_path = output_dir / "dune_candidate_feasibility_fixed.json"
            csv_path = output_dir / "dune_candidate_feasibility_wallets_fixed.csv"
            md_path = output_dir / "dune_candidate_feasibility_fixed.md"
            sql_path = output_dir / "dune_candidate_feasibility_sql_fixed.json"
            self.assertTrue(json_path.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(sql_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["execution_mode"], "dry_run")
            self.assertEqual(saved["generated_at"], 1000.0)
            combined_text = "\n".join(
                path.read_text(encoding="utf-8") for path in [json_path, csv_path, md_path, sql_path]
            )
            self.assertNotIn("api_key", combined_text.lower())
            self.assertNotIn("ivFG", combined_text)
            self.assertEqual(report["summary"]["candidate_wallets"], 1)


if __name__ == "__main__":
    unittest.main()
