import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_candidate_evidence_plan import write_wallet_candidate_evidence_plan
from wallets.wallet_candidate_evidence_plan import build_wallet_candidate_evidence_plan


class WalletCandidateEvidencePlanTests(unittest.TestCase):
    def test_plan_prioritizes_missing_replay_and_outcome_coverage(self):
        plan = build_wallet_candidate_evidence_plan(
            candidate_quality_review={
                "shortlist": [
                    {
                        "wallet": "WalletThin",
                        "quality_score": 84,
                        "recommendation": {"action": "OBSERVE_MORE"},
                        "replay": {"known_15m": 3, "fillable_events": 2},
                        "outcome": {"known_outcomes": 4},
                        "risk_flags": [],
                    }
                ]
            },
            min_replay_known=10,
            min_fillable=10,
            min_outcomes=10,
        )

        self.assertTrue(plan["review_only"])
        self.assertTrue(plan["live_execution_locked"])
        self.assertEqual(plan["summary"]["needs_replay_coverage"], 1)
        self.assertEqual(plan["summary"]["needs_outcome_coverage"], 1)
        row = plan["coverage_queue"][0]
        self.assertEqual(row["wallet"], "WalletThin")
        self.assertEqual(row["missing"]["replay_known_15m"], 7)
        self.assertEqual(row["missing"]["fillable_events"], 8)
        self.assertEqual(row["missing"]["known_outcomes"], 6)
        self.assertEqual(row["next_action"], "COLLECT_REPLAY_AND_OUTCOME_EVIDENCE")

    def test_plan_separates_risk_review_from_collection(self):
        plan = build_wallet_candidate_evidence_plan(
            candidate_quality_review={
                "shortlist": [
                    {
                        "wallet": "WalletRisk",
                        "quality_score": 78,
                        "recommendation": {"action": "RISK_REVIEW"},
                        "replay": {"known_15m": 12, "fillable_events": 12},
                        "outcome": {"known_outcomes": 12},
                        "risk_flags": ["sell-heavy observation"],
                    }
                ]
            }
        )

        self.assertEqual(plan["summary"]["risk_review"], 1)
        self.assertEqual(plan["coverage_queue"][0]["next_action"], "RESOLVE_RISK_FLAGS")

    def test_writer_persists_plan_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_candidate_evidence_plan.json"
            plan = write_wallet_candidate_evidence_plan(
                out_path=out,
                candidate_quality_review={
                    "shortlist": [
                        {
                            "wallet": "WalletA",
                            "quality_score": 50,
                            "recommendation": {"action": "OBSERVE_MORE"},
                            "replay": {},
                            "outcome": {},
                        }
                    ]
                },
            )

            self.assertTrue(out.exists())
            self.assertEqual(plan["summary"]["total_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
