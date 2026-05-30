import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_stage4_review import write_wallet_stage4_review_report
from wallets.wallet_stage4_review import build_wallet_stage4_review_report


def scorecard_row(wallet: str, **overrides):
    base = {
        "wallet": wallet,
        "recommendation_bucket": "paper_watch_candidate",
        "promotion_gate": "do_not_promote_yet",
        "trusted_promotion_allowed": False,
        "evidence_blockers": ["trusted_promotion_blocked", "missing_known_outcomes"],
        "next_action": "collect_outcome_labels",
        "enrichment": {
            "known_outcome_rows": 4,
            "rug_rows": 0,
            "runner_rows": 0,
            "missing_market_context_rows": 0,
        },
        "lifecycle": {
            "round_trip_lifecycles": 3,
            "lifecycle_mints": 4,
        },
    }
    base.update(overrides)
    return base


class WalletStage4ReviewTests(unittest.TestCase):
    def test_paper_watch_candidate_with_blockers_holds_for_more_data(self):
        report = build_wallet_stage4_review_report(
            wallet_evidence_scorecard={
                "summary": {"stage3_engine_completion_pct": 100, "wallet_score_readiness_pct": 0},
                "wallets": [scorecard_row("WalletA")],
            },
            generated_at=1234.0,
        )

        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["mode"], "WALLET_STAGE4_PROMOTION_DEMOTION_REVIEW_ONLY")
        row = report["reviews"][0]
        self.assertEqual(row["wallet"], "WalletA")
        self.assertEqual(row["stage4_action"], "HOLD_MORE_DATA")
        self.assertFalse(row["auto_apply"])
        self.assertIn("scorecard still has evidence blockers", row["reasons"])
        self.assertEqual(report["summary"]["hold_more_data"], 1)
        self.assertEqual(report["summary"]["auto_applied"], 0)

    def test_risk_review_and_hold_no_edge_route_to_manual_review(self):
        report = build_wallet_stage4_review_report(
            wallet_evidence_scorecard={
                "summary": {"stage3_engine_completion_pct": 100},
                "wallets": [
                    scorecard_row(
                        "RiskWallet",
                        recommendation_bucket="risk_review",
                        evidence_blockers=["manual_risk_review_required"],
                        next_action="manual_risk_review",
                    ),
                    scorecard_row(
                        "NoEdgeWallet",
                        recommendation_bucket="hold_no_edge",
                        evidence_blockers=["held_for_negative_or_rug_evidence"],
                        next_action="hold_out_of_paper_watch",
                    ),
                ],
            },
            generated_at=1234.0,
        )

        actions = {row["wallet"]: row["stage4_action"] for row in report["reviews"]}
        self.assertEqual(actions["RiskWallet"], "RISK_REVIEW_REQUIRED")
        self.assertEqual(actions["NoEdgeWallet"], "DEMOTION_OR_BLOCK_REVIEW")
        self.assertEqual(report["summary"]["risk_review_required"], 1)
        self.assertEqual(report["summary"]["demotion_or_block_review"], 1)

    def test_trusted_candidate_can_become_promotion_review_ready_when_all_gates_pass(self):
        report = build_wallet_stage4_review_report(
            wallet_evidence_scorecard={
                "summary": {"stage3_engine_completion_pct": 100, "wallet_score_readiness_pct": 80},
                "wallets": [
                    scorecard_row(
                        "TrustedWallet",
                        promotion_gate="trusted_review_possible",
                        trusted_promotion_allowed=True,
                        evidence_blockers=[],
                        enrichment={"known_outcome_rows": 25, "rug_rows": 0, "runner_rows": 10},
                        lifecycle={"round_trip_lifecycles": 5, "lifecycle_mints": 6},
                    )
                ],
            },
            generated_at=1234.0,
        )

        row = report["reviews"][0]
        self.assertEqual(row["stage4_action"], "PROMOTION_REVIEW_READY")
        self.assertFalse(row["auto_apply"])
        self.assertEqual(report["summary"]["promotion_review_ready"], 1)

    def test_writer_persists_stage4_review_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_stage4_review_report.json"
            report = write_wallet_stage4_review_report(
                out_path=out,
                wallet_evidence_scorecard={
                    "summary": {"stage3_engine_completion_pct": 100},
                    "wallets": [scorecard_row("WalletA")],
                },
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["wallets_reviewed"], 1)


if __name__ == "__main__":
    unittest.main()
