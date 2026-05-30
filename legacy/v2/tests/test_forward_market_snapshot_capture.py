import json
import tempfile
import unittest
from pathlib import Path

from utils.capture_forward_market_snapshot_repair_queue import write_forward_market_snapshot_capture
from wallets.forward_market_snapshot_capture import build_forward_market_snapshot_capture


def queue_row(mint="MintA", rows=3, start=100.0, end=1030.0):
    return {
        "token_mint": mint,
        "blocked_row_count": rows,
        "wallet_count": 2,
        "required_snapshot_start_time": start,
        "required_snapshot_end_time": end,
        "recommended_action": "collect_later_market_snapshot",
        "can_mutate_wallet_trust": False,
        "wallet_list_mutation_allowed": False,
    }


def provider(mint):
    return {
        "source": "dexscreener",
        "price": "0.01",
        "liquidity": {"usd": 12345},
        "marketCap": 100000,
        "pairAddress": f"pair-{mint}",
        "dex": "pumpswap",
        "url": f"https://dexscreener.test/{mint}",
    }


class ForwardMarketSnapshotCaptureTests(unittest.TestCase):
    def test_dry_run_selects_queue_rows_without_provider_calls(self):
        calls = []

        def tracking_provider(mint):
            calls.append(mint)
            return provider(mint)

        report = build_forward_market_snapshot_capture(
            repair_queue={"queue": [queue_row("MintA"), queue_row("MintB")]},
            existing_market_snapshots=[],
            market_provider=tracking_provider,
            execute=False,
            max_mints=1,
            max_market_context_calls=1,
            run_id="fixed",
            generated_at=2000.0,
        )

        self.assertEqual(report["summary"]["selected_mints"], 1)
        self.assertEqual(report["summary"]["dry_run_mints"], 1)
        self.assertEqual(report["summary"]["snapshots_captured"], 0)
        self.assertEqual(calls, [])
        self.assertEqual(report["selected_queue"][0]["token_mint"], "MintA")
        self.assertEqual(report["summary"]["wallet_list_mutations"], 0)
        self.assertEqual(report["summary"]["auto_trust_mutations"], 0)

    def test_dry_run_can_start_after_prior_batch(self):
        report = build_forward_market_snapshot_capture(
            repair_queue={"queue": [queue_row("MintA"), queue_row("MintB"), queue_row("MintC"), queue_row("MintD")]},
            existing_market_snapshots=[],
            execute=False,
            max_mints=2,
            start_index=2,
            max_market_context_calls=2,
            run_id="fixed",
            generated_at=2000.0,
        )

        self.assertEqual([row["token_mint"] for row in report["selected_queue"]], ["MintC", "MintD"])
        self.assertEqual(report["limits"]["start_index"], 2)
        self.assertEqual(report["summary"]["selected_mints"], 2)

    def test_execute_captures_snapshots_and_combines_with_existing(self):
        report = build_forward_market_snapshot_capture(
            repair_queue={"queue": [queue_row("MintA"), queue_row("MintB")]},
            existing_market_snapshots=[{"mint": "OldMint", "time": 50.0, "price": 0.5}],
            market_provider=provider,
            execute=True,
            max_mints=2,
            max_market_context_calls=2,
            run_id="fixed",
            generated_at=2000.0,
        )

        self.assertEqual(report["summary"]["snapshots_captured"], 2)
        self.assertEqual(report["summary"]["combined_market_snapshots"], 3)
        self.assertEqual(report["captured_snapshots"][0]["mint"], "MintA")
        self.assertEqual(report["captured_snapshots"][0]["time"], 2000.0)
        self.assertEqual(report["captured_snapshots"][0]["payload"]["repair_queue_source"], "market_snapshot_repair_queue")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_trust_mutation_allowed"])

    def test_execute_blocks_when_budget_exceeded(self):
        report = build_forward_market_snapshot_capture(
            repair_queue={"queue": [queue_row("MintA"), queue_row("MintB")]},
            existing_market_snapshots=[],
            market_provider=provider,
            execute=True,
            max_mints=2,
            max_market_context_calls=1,
            run_id="fixed",
            generated_at=2000.0,
        )

        self.assertEqual(report["summary"]["snapshots_captured"], 0)
        self.assertEqual(report["budget"]["budget_status"], "blocked_market_context_cycle_limit")
        self.assertEqual(report["captured_snapshots"], [])

    def test_writer_persists_report_snapshot_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_path = root / "queue.json"
            existing_path = root / "existing.jsonl"
            output_dir = root / "out"
            queue_path.write_text(json.dumps({"queue": [queue_row("MintA")]}), encoding="utf-8")
            existing_path.write_text(json.dumps({"mint": "OldMint", "time": 50.0, "price": 0.5}) + "\n", encoding="utf-8")

            report = write_forward_market_snapshot_capture(
                repair_queue_path=queue_path,
                existing_market_context_path=existing_path,
                output_dir=output_dir,
                market_provider=provider,
                execute=True,
                max_mints=1,
                max_market_context_calls=1,
                run_id="fixed",
                generated_at=2000.0,
            )

            self.assertEqual(report["summary"]["snapshots_captured"], 1)
            self.assertTrue((output_dir / "forward_market_snapshot_capture_fixed.json").exists())
            self.assertTrue((output_dir / "forward_market_snapshot_capture_snapshots_fixed.jsonl").exists())
            self.assertTrue((output_dir / "forward_market_snapshot_capture_combined_market_context_fixed.jsonl").exists())
            self.assertTrue((output_dir / "forward_market_snapshot_capture_fixed.md").exists())


if __name__ == "__main__":
    unittest.main()
