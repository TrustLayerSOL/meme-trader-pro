import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_candidate_backfill_targets import write_wallet_candidate_backfill_targets
from wallets.wallet_candidate_backfill_targets import build_wallet_candidate_backfill_targets


class WalletCandidateBackfillTargetsTests(unittest.TestCase):
    def test_targets_existing_unknown_replay_events_for_outcome_label_backfill(self):
        report = build_wallet_candidate_backfill_targets(
            candidate_evidence_plan={
                "coverage_queue": [
                    {
                        "wallet": "WalletNeedsLabels",
                        "priority_score": 70,
                        "quality_score": 82,
                        "next_action": "COLLECT_REPLAY_AND_OUTCOME_EVIDENCE",
                        "missing": {"replay_known_15m": 2, "fillable_events": 1, "known_outcomes": 2},
                    }
                ]
            },
            replay_events=[
                {
                    "event_id": "event_1",
                    "mint": "MintA",
                    "source_record_type": "rejected_signal",
                    "signal_timestamp": 123,
                    "wallets": [{"wallet": "WalletNeedsLabels"}],
                    "execution_assumptions": {"fill_status": "fillable_with_assumptions"},
                    "later_outcome": {"windows": {"15m": {"outcome_type": "unknown"}}},
                }
            ],
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["summary"]["needs_outcome_label_backfill"], 1)
        row = report["targets"][0]
        self.assertEqual(row["wallet"], "WalletNeedsLabels")
        self.assertEqual(row["next_collection_step"], "BACKFILL_OUTCOME_LABELS")
        self.assertEqual(row["local_replay_events"], 1)
        self.assertEqual(row["unknown_15m_events"], 1)
        self.assertEqual(row["event_targets"][0]["mint"], "MintA")

    def test_targets_wallet_history_when_no_local_replay_events_exist(self):
        report = build_wallet_candidate_backfill_targets(
            candidate_evidence_plan={
                "coverage_queue": [
                    {
                        "wallet": "WalletNoEvents",
                        "priority_score": 60,
                        "quality_score": 78,
                        "next_action": "COLLECT_REPLAY_AND_OUTCOME_EVIDENCE",
                        "missing": {"replay_known_15m": 10, "fillable_events": 10, "known_outcomes": 10},
                    }
                ]
            },
            replay_events=[],
        )

        self.assertEqual(report["summary"]["needs_wallet_history"], 1)
        self.assertEqual(report["targets"][0]["next_collection_step"], "COLLECT_WALLET_HISTORY")

    def test_writer_persists_target_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_candidate_backfill_targets.json"
            replay = Path(tmp) / "replay_events.jsonl"
            replay.write_text("", encoding="utf-8")

            report = write_wallet_candidate_backfill_targets(
                out_path=out,
                replay_events_path=replay,
                candidate_evidence_plan={"coverage_queue": []},
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["total_targets"], 0)


if __name__ == "__main__":
    unittest.main()
