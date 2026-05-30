import unittest

from wallets.forward_free_rpc_canary import build_forward_free_rpc_canary_report


def fake_cycle_factory(reports):
    calls = []

    def fake_cycle(**kwargs):
        calls.append(kwargs)
        return reports[len(calls) - 1]

    fake_cycle.calls = calls
    return fake_cycle


class ForwardFreeRpcCanaryTests(unittest.TestCase):
    def test_canary_aggregates_small_forward_collection_cycles(self):
        fake_cycle = fake_cycle_factory([
            {
                "rpc_mode": "free_public_rpc",
                "paid_rpc_allowed": False,
                "summary": {
                    "wallets_processed": 5,
                    "wallets_collected": 2,
                    "wallets_blocked_rpc_error": 1,
                    "wallets_blocked_rpc_preflight": 0,
                    "wallets_throttled_by_rpc_preflight": 3,
                    "evidence_rows_created": 4,
                },
                "api_budget": {
                    "estimated_rpc_calls_per_cycle": 30,
                    "projected_rpc_calls_per_day": 8640,
                    "budget_status": "within_budget",
                },
                "rpc_preflight": {"status": "degraded"},
                "market_context": {"summary": {"snapshots_collected": 3}},
            },
            {
                "rpc_mode": "free_public_rpc",
                "paid_rpc_allowed": False,
                "summary": {
                    "wallets_processed": 5,
                    "wallets_collected": 1,
                    "wallets_blocked_rpc_error": 0,
                    "wallets_blocked_rpc_preflight": 0,
                    "wallets_throttled_by_rpc_preflight": 0,
                    "evidence_rows_created": 2,
                },
                "api_budget": {
                    "estimated_rpc_calls_per_cycle": 30,
                    "projected_rpc_calls_per_day": 8640,
                    "budget_status": "within_budget",
                },
                "rpc_preflight": {"status": "healthy"},
                "market_context": {"summary": {"snapshots_collected": 2}},
            },
        ])

        report = build_forward_free_rpc_canary_report(
            cycle_runner=fake_cycle,
            sleep=lambda _seconds: None,
            duration_seconds=600,
            cycle_interval_seconds=300,
            max_wallets=10,
            adaptive_degraded_max_wallets=5,
        )

        self.assertEqual(report["mode"], "FORWARD_FREE_RPC_CANARY_REVIEW_ONLY")
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["paid_rpc_allowed"])
        self.assertEqual(report["summary"]["cycles_attempted"], 2)
        self.assertEqual(report["summary"]["wallets_processed"], 10)
        self.assertEqual(report["summary"]["evidence_rows_created"], 6)
        self.assertEqual(report["summary"]["market_snapshots_collected"], 5)
        self.assertEqual(report["summary"]["wallets_throttled_by_rpc_preflight"], 3)
        self.assertEqual(report["provider_status_counts"], {"degraded": 1, "healthy": 1})
        self.assertEqual(report["recommendation"], "FREE_RPC_USABLE_SMALL_THROTTLED")
        self.assertTrue(all(call["rpc_preflight"] for call in fake_cycle.calls))
        self.assertTrue(all(call["adaptive_free_rpc_throttle"] for call in fake_cycle.calls))
        self.assertTrue(all(not call["paid_rpc_allowed"] for call in fake_cycle.calls))

    def test_canary_blocks_before_running_when_projected_daily_budget_is_too_high(self):
        fake_cycle = fake_cycle_factory([])

        report = build_forward_free_rpc_canary_report(
            cycle_runner=fake_cycle,
            sleep=lambda _seconds: None,
            duration_seconds=1800,
            cycle_interval_seconds=60,
            max_wallets=50,
            signature_limit=40,
            max_transactions_per_wallet=20,
            max_rpc_calls_per_day=120_000,
        )

        self.assertEqual(fake_cycle.calls, [])
        self.assertEqual(report["recommendation"], "BLOCKED_BUDGET")
        self.assertFalse(report["budget"]["execute_allowed"])
        self.assertEqual(report["summary"]["cycles_attempted"], 0)

    def test_canary_recommends_unstable_when_preflight_or_rpc_errors_dominate(self):
        fake_cycle = fake_cycle_factory([
            {
                "rpc_mode": "free_public_rpc",
                "paid_rpc_allowed": False,
                "summary": {
                    "wallets_processed": 0,
                    "wallets_collected": 0,
                    "wallets_blocked_rpc_error": 0,
                    "wallets_blocked_rpc_preflight": 10,
                    "wallets_throttled_by_rpc_preflight": 0,
                    "evidence_rows_created": 0,
                },
                "api_budget": {"estimated_rpc_calls_per_cycle": 50, "budget_status": "within_budget"},
                "rpc_preflight": {"status": "blocked_unhealthy"},
                "market_context": {"summary": {"snapshots_collected": 0}},
            }
        ])

        report = build_forward_free_rpc_canary_report(
            cycle_runner=fake_cycle,
            sleep=lambda _seconds: None,
            duration_seconds=300,
            cycle_interval_seconds=300,
            max_wallets=10,
        )

        self.assertEqual(report["summary"]["wallets_blocked_rpc_preflight"], 10)
        self.assertEqual(report["recommendation"], "FREE_RPC_UNSTABLE")
        self.assertIn("blocked_unhealthy", report["blockers"])


if __name__ == "__main__":
    unittest.main()
