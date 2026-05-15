import unittest

from wallets.wallet_candidate_audit import build_wallet_candidate_audit


class WalletCandidateAuditTests(unittest.TestCase):
    def ledger_row(self, wallet, action="PROMOTION_REVIEW", known=24):
        return {
            "wallet": wallet,
            "total_signals": known + 2,
            "accepted_signals": 0,
            "rejected_signals": known + 2,
            "known_outcomes": known,
            "runner_participation": 14 if action == "PROMOTION_REVIEW" else 2,
            "rug_participation": 0 if action == "PROMOTION_REVIEW" else 5,
            "dead_participation": 0 if action == "PROMOTION_REVIEW" else 12,
            "runner_participation_rate": 0.58 if action == "PROMOTION_REVIEW" else 0.08,
            "rug_participation_rate": 0.0 if action == "PROMOTION_REVIEW" else 0.2,
            "average_pnl_after_signal": 74.2 if action == "PROMOTION_REVIEW" else -31.5,
            "promotion_score": 94.5 if action == "PROMOTION_REVIEW" else 2,
            "demotion_score": 0 if action == "PROMOTION_REVIEW" else 45,
            "confidence": {"sample_quality": "usable", "known_outcome_rate": 0.86},
            "recommendation": {"action": action, "review_only": True, "reasons": ["test reason"]},
        }

    def test_audit_includes_review_candidates_and_blocks_apply(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={
                "wallets": {
                    "WalletA": self.ledger_row("WalletA", "PROMOTION_REVIEW"),
                    "WalletB": self.ledger_row("WalletB", "DEMOTION_REVIEW"),
                    "WalletC": self.ledger_row("WalletC", "HOLD_MORE_DATA"),
                }
            },
            baseline_comparison={
                "wallets": [
                    {"wallet": "WalletA", "comparison_status": "LEDGER_STRONGER_SIGNAL"},
                    {"wallet": "WalletB", "comparison_status": "LEDGER_STRONGER_SIGNAL"},
                ]
            },
        )

        self.assertEqual(report["counts"]["candidates"], 2)
        self.assertEqual(report["counts"]["promotion_review"], 1)
        self.assertEqual(report["counts"]["demotion_review"], 1)
        self.assertTrue(report["review_only"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertEqual(report["candidates"][0]["audit_status"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(report["candidates"][0]["comparison_status"], "LEDGER_STRONGER_SIGNAL")

    def test_thin_candidate_is_flagged_even_if_recommendation_is_present(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={"wallets": {"WalletA": self.ledger_row("WalletA", "PROMOTION_REVIEW", known=5)}},
            baseline_comparison={"wallets": []},
        )

        candidate = report["candidates"][0]
        self.assertEqual(candidate["audit_status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(candidate["evidence_gates"]["known_outcome_sample_passed"])
        self.assertIn("known outcome sample below audit threshold", candidate["audit_notes"])

    def test_applied_promotion_moves_to_resolved_candidates(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={
                "wallets": {
                    "WalletA": self.ledger_row("WalletA", "PROMOTION_REVIEW"),
                    "WalletB": self.ledger_row("WalletB", "DEMOTION_REVIEW"),
                }
            },
            baseline_comparison={"wallets": []},
            review_decisions={
                "decisions": [
                    {"wallet": "WalletA", "decision": "approve_promotion", "approved": True},
                ]
            },
            tracked_wallets=[{"trackedWalletAddress": "WalletA"}],
        )

        self.assertEqual(report["counts"]["candidates"], 1)
        self.assertEqual(report["counts"]["resolved"], 1)
        self.assertEqual(report["candidates"][0]["wallet"], "WalletB")
        resolved = report["resolved_candidates"][0]
        self.assertEqual(resolved["wallet"], "WalletA")
        self.assertEqual(resolved["audit_status"], "RESOLVED_APPLIED")
        self.assertTrue(resolved["review_resolved"])
        self.assertEqual(resolved["resolution"]["decision"], "approve_promotion")

    def test_approved_promotion_stays_active_until_wallet_is_tracked(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={"wallets": {"WalletA": self.ledger_row("WalletA", "PROMOTION_REVIEW")}},
            baseline_comparison={"wallets": []},
            review_decisions={
                "decisions": [
                    {"wallet": "WalletA", "decision": "approve_promotion", "approved": True},
                ]
            },
            tracked_wallets=[],
        )

        self.assertEqual(report["counts"]["candidates"], 1)
        self.assertEqual(report["counts"]["resolved"], 0)
        self.assertFalse(report["candidates"][0]["review_resolved"])

    def test_replay_review_decisions_become_candidate_audit_rows(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={"wallets": {}},
            baseline_comparison={"wallets": []},
            review_decisions={
                "decisions": [
                    {
                        "wallet": "ReplayPromote",
                        "decision": "approve_promotion",
                        "approved": True,
                        "source": "wallet_replay_review",
                        "note": "runner-heavy replay evidence",
                        "replay_metrics": {
                            "known_15m": 12,
                            "fillable_events": 12,
                            "runner_rate_known_15m": 0.75,
                            "rug_rate_known_15m": 0,
                            "runner_minus_rug_rate_15m": 0.75,
                        },
                    },
                    {
                        "wallet": "ReplayDemote",
                        "decision": "approve_demotion",
                        "approved": True,
                        "source": "wallet_replay_review",
                        "replay_metrics": {
                            "known_15m": 14,
                            "fillable_events": 14,
                            "runner_rate_known_15m": 0.1,
                            "rug_rate_known_15m": 0.2,
                            "runner_minus_rug_rate_15m": -0.1,
                        },
                    },
                ]
            },
            tracked_wallets=[],
        )

        rows = {row["wallet"]: row for row in report["candidates"]}
        self.assertEqual(report["counts"]["promotion_review"], 1)
        self.assertEqual(report["counts"]["demotion_review"], 1)
        self.assertEqual(rows["ReplayPromote"]["recommendation_action"], "PROMOTION_REVIEW")
        self.assertEqual(rows["ReplayPromote"]["comparison_status"], "REPLAY_REVIEW_STRONG_SIGNAL")
        self.assertTrue(rows["ReplayPromote"]["evidence_gates"]["known_outcome_sample_passed"])
        self.assertEqual(rows["ReplayPromote"]["evidence"]["known_outcomes"], 12)
        self.assertEqual(rows["ReplayPromote"]["evidence"]["source"], "wallet_replay_review")
        self.assertEqual(rows["ReplayDemote"]["recommendation_action"], "DEMOTION_REVIEW")

    def test_replay_approved_promotion_resolves_after_wallet_is_tracked(self):
        report = build_wallet_candidate_audit(
            outcome_ledger={"wallets": {}},
            baseline_comparison={"wallets": []},
            review_decisions={
                "decisions": [
                    {
                        "wallet": "ReplayPromote",
                        "decision": "approve_promotion",
                        "approved": True,
                        "source": "wallet_replay_review",
                        "replay_metrics": {
                            "known_15m": 12,
                            "fillable_events": 12,
                            "runner_rate_known_15m": 0.75,
                            "rug_rate_known_15m": 0,
                            "runner_minus_rug_rate_15m": 0.75,
                        },
                    },
                ]
            },
            tracked_wallets=[{"trackedWalletAddress": "ReplayPromote"}],
        )

        self.assertEqual(report["counts"]["candidates"], 0)
        self.assertEqual(report["counts"]["resolved"], 1)
        resolved = report["resolved_candidates"][0]
        self.assertEqual(resolved["wallet"], "ReplayPromote")
        self.assertEqual(resolved["audit_status"], "RESOLVED_APPLIED")
        self.assertEqual(resolved["resolution"]["decision"], "approve_promotion")


if __name__ == "__main__":
    unittest.main()
