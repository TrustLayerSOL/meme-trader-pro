import json
import tempfile
import unittest
from pathlib import Path

from utils.capture_candidate_bounded_snapshots import write_candidate_bounded_snapshot_capture
from wallets.candidate_bounded_snapshot_capture import build_candidate_bounded_snapshot_capture


def queue_row(mint="MintA", *, wallet="WalletA", start=100.0, end=1000.0):
    return {
        "event_id": f"{wallet}|Sig|{mint}|buy|100",
        "wallet_address": wallet,
        "token_address": mint,
        "signal_time": start,
        "needed_snapshot_start": start,
        "needed_snapshot_end": end,
        "recommended_action": "capture_later_market_snapshot",
        "wallet_trust_mutation_allowed": False,
        "wallet_list_mutation_allowed": False,
    }


def provider(mint):
    return {
        "source": "dexscreener",
        "price": "0.01",
        "liquidity": {"usd": 12345},
        "marketCap": 100000,
        "url": f"https://dexscreener.test/{mint}",
    }


class CandidateBoundedSnapshotCaptureTests(unittest.TestCase):
    def test_captures_only_windows_that_are_still_open_and_within_budget(self):
        calls = []

        def tracking_provider(mint):
            calls.append(mint)
            return provider(mint)

        report = build_candidate_bounded_snapshot_capture(
            outcome_completion={"capture_queue": [queue_row("MintOpen", end=1200.0), queue_row("MintExpired", end=900.0)]},
            market_provider=tracking_provider,
            execute=True,
            max_market_context_calls=2,
            generated_at=1000.0,
            run_id="fixed",
        )

        self.assertEqual(calls, ["MintOpen"])
        self.assertEqual(report["summary"]["current_snapshots_captured"], 1)
        self.assertEqual(report["summary"]["deferred_expired_window_rows"], 1)
        self.assertEqual(report["summary"]["provider_misses"], 0)
        self.assertEqual(report["captured_snapshots"][0]["mint"], "MintOpen")
        self.assertEqual(report["deferred_queue"][0]["recommended_next_action"], "archival_or_onchain_later_snapshot_recovery")
        self.assertFalse(report["wallet_trust_mutation_allowed"])
        self.assertFalse(report["wallet_list_mutation_allowed"])

    def test_dry_run_and_budget_do_not_call_provider(self):
        calls = []

        def tracking_provider(mint):
            calls.append(mint)
            return provider(mint)

        report = build_candidate_bounded_snapshot_capture(
            outcome_completion={"capture_queue": [queue_row("MintA", end=1200.0), queue_row("MintB", end=1200.0)]},
            market_provider=tracking_provider,
            execute=True,
            max_market_context_calls=1,
            generated_at=1000.0,
            run_id="fixed",
        )

        self.assertEqual(calls, [])
        self.assertEqual(report["budget"]["budget_status"], "blocked_market_context_cycle_limit")
        self.assertEqual(report["summary"]["current_snapshots_captured"], 0)

        dry_run = build_candidate_bounded_snapshot_capture(
            outcome_completion={"capture_queue": [queue_row("MintA", end=1200.0)]},
            market_provider=tracking_provider,
            execute=False,
            max_market_context_calls=1,
            generated_at=1000.0,
            run_id="fixed",
        )
        self.assertEqual(dry_run["summary"]["dry_run_capture_eligible_rows"], 1)
        self.assertEqual(calls, [])

    def test_writer_exports_deterministic_json_csv_jsonl_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_path = root / "completion.json"
            output_dir = root / "out"
            queue_path.write_text(json.dumps({"capture_queue": [queue_row("MintOpen", end=1200.0)]}, sort_keys=True), encoding="utf-8")

            report = write_candidate_bounded_snapshot_capture(
                outcome_completion_path=queue_path,
                output_dir=output_dir,
                market_provider=provider,
                execute=True,
                max_market_context_calls=1,
                run_id="fixed",
                generated_at=1000.0,
            )

            self.assertTrue((output_dir / "candidate_bounded_snapshot_capture_fixed.json").exists())
            self.assertTrue((output_dir / "candidate_bounded_snapshot_capture_snapshots_fixed.jsonl").exists())
            self.assertTrue((output_dir / "candidate_bounded_snapshot_capture_deferred_fixed.csv").exists())
            self.assertTrue((output_dir / "candidate_bounded_snapshot_capture_fixed.md").exists())
            saved = json.loads((output_dir / "candidate_bounded_snapshot_capture_fixed.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["summary"], report["summary"])
            self.assertIn("Candidate Bounded Snapshot Capture", (output_dir / "candidate_bounded_snapshot_capture_fixed.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
