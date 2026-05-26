import json
import tempfile
import unittest
from pathlib import Path

from utils.build_dune_candidate_resolver_adapter import write_dune_candidate_resolver_adapter
from wallets.dune_candidate_resolver_adapter import build_dune_candidate_resolver_adapter


WALLET = "2K5DekX2pitRReFBC4byUCv2Ci3o89StnBQnBbkA9BdN"


def blocked_event(event_id="E1", *, price_context=False):
    context = {}
    if price_context:
        context = {"price": 0.01, "execution_price_quote": 0.01}
    return {
        "event_id": event_id,
        "wallet": WALLET,
        "token_mint": "MintA",
        "signal_time": 1000.0,
        "transaction_signature": "SigLocal",
        "status": "blocked_missing_forward_entry_context",
        "block_reasons": ["missing_forward_entry_price"],
        "decision_context": {"estimated_entry_context": context},
        "wallet_list_mutation_allowed": False,
        "can_mutate_wallet_trust": False,
    }


def join_event(event_id="E1", *, price=0.0123):
    return {
        "event_id": event_id,
        "wallet_address": WALLET,
        "token_mint": "MintA",
        "local_transaction_signature": "SigLocal",
        "dune_transaction_signature": "SigDune",
        "local_signal_time": 1000.0,
        "dune_block_time": "1970-01-01 00:16:40.000 UTC",
        "time_delta_seconds": 0.0,
        "match_type": "signature_exact",
        "amount_usd": 25.0,
        "price_usd": price,
        "has_quote_anchor_candidate": True,
        "has_price_context_candidate": price is not None,
        "has_liquidity_context": False,
        "has_market_cap_context": False,
        "proof_ready": False,
        "evidence_quality": "dune_quote_price_candidate_not_score_ready",
        "missing_for_proof": ["liquidity", "market_cap"],
    }


class DuneCandidateResolverAdapterTests(unittest.TestCase):
    def test_augments_joined_events_but_keeps_rows_blocked_not_proof_ready(self):
        report = build_dune_candidate_resolver_adapter(
            records=[blocked_event()],
            dune_join={"joined_events": [join_event()]},
            generated_at=1000.0,
        )

        self.assertEqual(report["summary"]["joined_events_scanned"], 1)
        self.assertEqual(report["summary"]["context_candidate_records"], 1)
        self.assertEqual(report["summary"]["price_candidate_records"], 1)
        self.assertEqual(report["summary"]["proof_ready_records"], 0)
        self.assertEqual(report["summary"]["wallet_trust_mutations"], 0)
        record = report["context_candidate_records"][0]
        ctx = record["decision_context"]["estimated_entry_context"]
        self.assertEqual(record["status"], "blocked_missing_forward_entry_context")
        self.assertIn("dune_context_not_score_ready", record["block_reasons"])
        self.assertIn("missing_forward_liquidity", record["block_reasons"])
        self.assertIn("missing_forward_market_cap", record["block_reasons"])
        self.assertEqual(ctx["price"], 0.0123)
        self.assertEqual(ctx["price_source"], "dune_dex_trade_candidate")
        self.assertEqual(ctx["dune_dex_trade_candidate"]["match_type"], "signature_exact")
        self.assertFalse(record["dune_context_candidate"]["proof_ready"])
        self.assertFalse(record["can_mutate_wallet_trust"])
        self.assertFalse(record["wallet_list_mutation_allowed"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_quote_only_match_is_preserved_without_price_repair(self):
        report = build_dune_candidate_resolver_adapter(
            records=[blocked_event()],
            dune_join={"joined_events": [join_event(price=None)]},
            generated_at=1000.0,
        )

        record = report["context_candidate_records"][0]
        ctx = record["decision_context"]["estimated_entry_context"]
        self.assertNotIn("price", ctx)
        self.assertEqual(ctx["dune_amount_usd"], 25.0)
        self.assertEqual(report["summary"]["price_candidate_records"], 0)
        self.assertEqual(report["summary"]["quote_only_candidate_records"], 1)

    def test_writer_exports_json_jsonl_csv_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records_path = root / "records.jsonl"
            join_path = root / "join.json"
            output_dir = root / "out"
            records_path.write_text(json.dumps(blocked_event(), sort_keys=True) + "\n", encoding="utf-8")
            join_path.write_text(json.dumps({"joined_events": [join_event()]}, sort_keys=True), encoding="utf-8")

            report = write_dune_candidate_resolver_adapter(
                records_path=records_path,
                dune_join_path=join_path,
                output_dir=output_dir,
                run_id="fixed",
                generated_at=1000.0,
            )

            json_path = output_dir / "dune_candidate_resolver_adapter_fixed.json"
            records_out = output_dir / "dune_candidate_context_candidate_records_fixed.jsonl"
            csv_path = output_dir / "dune_candidate_resolver_adapter_events_fixed.csv"
            md_path = output_dir / "dune_candidate_resolver_adapter_fixed.md"
            self.assertTrue(json_path.exists())
            self.assertTrue(records_out.exists())
            self.assertTrue(csv_path.exists())
            self.assertTrue(md_path.exists())
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("dune_context_not_score_ready", records_out.read_text(encoding="utf-8"))
            self.assertIn("dune_price_candidate", csv_path.read_text(encoding="utf-8"))
            self.assertIn("Dune Candidate Resolver Adapter", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
