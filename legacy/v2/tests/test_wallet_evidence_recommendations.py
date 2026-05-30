import tempfile
import unittest
from pathlib import Path

from utils.build_wallet_evidence_recommendations import write_wallet_evidence_recommendations_report
from wallets.wallet_evidence_recommendations import build_wallet_evidence_recommendations


def readiness(score_ready: int = 0) -> dict:
    return {
        "summary": {
            "wallet_score_readiness_pct": score_ready,
            "score_ready_market_context_records": 0,
        }
    }


def history_row(
    wallet: str,
    *,
    usable: int,
    unique_mints: int = 1,
    rug_rate: float = 0.0,
    repeated_rugs: int = 0,
    min_needed: int = 0,
) -> dict:
    return {
        "wallet": wallet,
        "target_status": "partial_wallet_history_collected",
        "evidence_rows_created": usable,
        "buy_events": usable,
        "sell_events": 0,
        "unique_mints": unique_mints,
        "metrics": {
            "total_usable_evidence_rows": usable,
            "rug_participation_rate": rug_rate,
            "repeated_rug_association": repeated_rugs,
            "minimum_additional_evidence_needed": min_needed,
            "evidence_confidence_score": 90,
        },
    }


class WalletEvidenceRecommendationTests(unittest.TestCase):
    def test_risk_flag_targets_are_risk_review_and_not_auto_applied(self):
        report = build_wallet_evidence_recommendations(
            candidate_backfill_targets={
                "summary": {"total_targets": 1},
                "targets": [
                    {
                        "wallet": "RiskWallet",
                        "risk_flags": ["late-buyer"],
                        "next_collection_step": "REVIEW_RISK_FLAGS_FIRST",
                    }
                ],
            },
            wallet_history_backfill={"summary": {}, "wallets": []},
            wallet_evidence_readiness=readiness(),
        )

        row = report["recommendations"][0]
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(row["bucket"], "risk_review")
        self.assertIn("do_not_promote_yet", row["labels"])
        self.assertFalse(row["auto_apply"])
        self.assertEqual(report["summary"]["risk_review"], 1)

    def test_known_rug_exposure_is_held_out_of_paper_watch(self):
        report = build_wallet_evidence_recommendations(
            candidate_backfill_targets={
                "summary": {"total_targets": 1},
                "targets": [{"wallet": "RugWallet", "risk_flags": []}],
            },
            wallet_history_backfill={
                "summary": {"ready_for_candidate_review": 1},
                "wallets": [
                    history_row("RugWallet", usable=16, unique_mints=3, rug_rate=1.0, repeated_rugs=1)
                ],
            },
            wallet_evidence_readiness=readiness(),
        )

        row = report["recommendations"][0]
        self.assertEqual(row["bucket"], "hold_no_edge")
        self.assertIn("known_rug_exposure", row["reason_codes"])
        self.assertEqual(report["summary"]["hold_no_edge"], 1)

    def test_usable_evidence_becomes_paper_watch_candidate_but_not_trusted(self):
        report = build_wallet_evidence_recommendations(
            candidate_backfill_targets={
                "summary": {"total_targets": 1},
                "targets": [{"wallet": "WatchWallet", "risk_flags": []}],
            },
            wallet_history_backfill={
                "summary": {"ready_for_candidate_review": 1},
                "wallets": [history_row("WatchWallet", usable=20, unique_mints=5)],
            },
            wallet_evidence_readiness=readiness(score_ready=0),
        )

        row = report["recommendations"][0]
        self.assertEqual(row["bucket"], "paper_watch_candidate")
        self.assertEqual(row["promotion_gate"], "do_not_promote_yet")
        self.assertIn("paper_watch_candidate", row["labels"])
        self.assertIn("do_not_promote_yet", row["labels"])
        self.assertFalse(row["trusted_promotion_allowed"])
        self.assertEqual(report["summary"]["paper_watch_candidate"], 1)
        self.assertEqual(report["summary"]["do_not_promote_yet"], 1)

    def test_thin_history_stays_observe_more(self):
        report = build_wallet_evidence_recommendations(
            candidate_backfill_targets={
                "summary": {"total_targets": 1},
                "targets": [{"wallet": "ThinWallet", "risk_flags": []}],
            },
            wallet_history_backfill={
                "summary": {"ready_for_candidate_review": 0},
                "wallets": [history_row("ThinWallet", usable=4, unique_mints=1, min_needed=6)],
            },
            wallet_evidence_readiness=readiness(),
        )

        row = report["recommendations"][0]
        self.assertEqual(row["bucket"], "observe_more")
        self.assertIn("insufficient_wallet_history", row["reason_codes"])
        self.assertEqual(report["summary"]["observe_more"], 1)

    def test_writer_persists_recommendation_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "wallet_evidence_recommendations_report.json"
            report = write_wallet_evidence_recommendations_report(
                out_path=out,
                candidate_backfill_targets={
                    "summary": {"total_targets": 1},
                    "targets": [{"wallet": "WatchWallet", "risk_flags": []}],
                },
                wallet_history_backfill={
                    "summary": {"ready_for_candidate_review": 1},
                    "wallets": [history_row("WatchWallet", usable=12, unique_mints=2)],
                },
                wallet_evidence_readiness=readiness(),
            )

            self.assertTrue(out.exists())
            self.assertEqual(report["summary"]["wallets_reviewed"], 1)


if __name__ == "__main__":
    unittest.main()
