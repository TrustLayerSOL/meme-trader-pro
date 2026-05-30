import tempfile
import unittest
from pathlib import Path

from utils.build_forward_public_rpc_schedule_proposal import write_forward_public_rpc_schedule_proposal
from wallets.forward_public_rpc_schedule_proposal import build_forward_public_rpc_schedule_proposal


def canary(recommendation="FREE_RPC_USABLE_SMALL_THROTTLED", blockers=None, rpc_day=8640):
    return {
        "recommendation": recommendation,
        "blockers": blockers or [],
        "paid_rpc_allowed": False,
        "live_execution_locked": True,
        "summary": {
            "cycles_attempted": 1,
            "wallets_processed": 10,
            "evidence_rows_created": 15,
            "market_snapshots_collected": 14,
        },
        "provider_status_counts": {"healthy": 1},
        "budget": {"projected_rpc_calls_per_day": rpc_day},
    }


class ForwardPublicRpcScheduleProposalTests(unittest.TestCase):
    def test_three_usable_canaries_prepare_conservative_schedule_without_enabling_it(self):
        report = build_forward_public_rpc_schedule_proposal(
            canary_reports=[canary(), canary(), canary()],
            provider_report={
                "recommendation": "USE_HEALTHY_FREE_PROVIDER",
                "recommended_free_rpc_safe_urls": [
                    "https://api.mainnet-beta.solana.com",
                    "https://solana-rpc.publicnode.com",
                ],
            },
            generated_at=1_700_000_000,
        )

        self.assertEqual(report["mode"], "FORWARD_PUBLIC_RPC_SCHEDULE_PROPOSAL_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertFalse(report["schedule_enabled"])
        self.assertFalse(report["paid_rpc_allowed"])
        self.assertTrue(report["live_execution_locked"])
        self.assertEqual(report["wallet_list_mutations"], 0)
        self.assertEqual(report["trust_mutations"], 0)
        self.assertEqual(report["stable_canaries"], 3)
        self.assertEqual(report["recommendation"], "READY_FOR_CONSERVATIVE_RECURRING_PROPOSAL")
        self.assertEqual(report["proposed_schedule"]["max_wallets"], 10)
        self.assertEqual(report["proposed_schedule"]["interval_seconds"], 900)
        self.assertEqual(report["proposed_schedule"]["max_rpc_calls_per_day"], 120_000)
        self.assertIn("stop_on_provider_error", report["proposed_schedule"]["stop_rules"])

    def test_unstable_canary_blocks_recurring_schedule(self):
        report = build_forward_public_rpc_schedule_proposal(
            canary_reports=[canary(), canary(blockers=["high_rpc_error_rate"])],
            provider_report={"recommendation": "USE_HEALTHY_FREE_PROVIDER"},
        )

        self.assertEqual(report["recommendation"], "KEEP_MANUAL_ON_DEMAND_ONLY")
        self.assertFalse(report["schedule_enabled"])
        self.assertEqual(report["proposed_schedule"], {})
        self.assertIn("needs_three_stable_canaries", report["blockers"])

    def test_projected_budget_over_cap_blocks_proposal(self):
        report = build_forward_public_rpc_schedule_proposal(
            canary_reports=[canary(rpc_day=130_000), canary(), canary()],
            provider_report={"recommendation": "USE_HEALTHY_FREE_PROVIDER"},
        )

        self.assertEqual(report["recommendation"], "KEEP_MANUAL_ON_DEMAND_ONLY")
        self.assertIn("projected_rpc_day_exceeds_cap", report["blockers"])

    def test_writer_persists_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = write_forward_public_rpc_schedule_proposal(
                out_path=Path(tmp) / "proposal.json",
                canary_reports=[canary(), canary(), canary()],
                provider_report={"recommendation": "USE_HEALTHY_FREE_PROVIDER"},
                generated_at=1_700_000_000,
            )

            self.assertEqual(report["recommendation"], "READY_FOR_CONSERVATIVE_RECURRING_PROPOSAL")
            self.assertTrue(Path(tmp, "proposal.json").exists())
            self.assertEqual(len(list(Path(tmp).glob("forward_public_rpc_schedule_proposal_*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
