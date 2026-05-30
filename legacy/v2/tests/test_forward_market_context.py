import unittest
from unittest.mock import patch

from wallets.forward_market_context import build_forward_market_context_report
from wallets.forward_market_context import fetch_dexscreener_market_info


class FakeMarketProvider:
    def __init__(self):
        self.calls = []

    def __call__(self, mint):
        self.calls.append(mint)
        return {
            "source": "dexscreener",
            "price": 0.01,
            "liquidity": 25_000,
            "market_cap": 100_000,
            "fdv": 100_000,
            "url": f"https://dexscreener.test/{mint}",
            "tx_count_m5": 12,
        }


class ForwardMarketContextTests(unittest.TestCase):
    def evidence_row(self, *, mint="MintA", timestamp=995.0):
        return {
            "wallet": "WalletA",
            "token_mint": mint,
            "observed_action": "buy",
            "timestamp": timestamp,
            "transaction_signature": "SigA",
            "estimated_entry_context": {"price": None, "decision_time_safe": True},
            "estimated_exit_context": {"price": None, "decision_time_safe": True},
            "later_token_outcome": {"outcome_type": "pending_forward_outcome"},
            "missing_fields": ["entry_price", "exit_price", "later_token_outcome"],
            "risk_flags": ["forward_current_activity"],
            "confidence_score": 70,
        }

    def test_captures_unique_mints_and_attaches_near_event_context(self):
        provider = FakeMarketProvider()
        report = build_forward_market_context_report(
            evidence_records=[
                self.evidence_row(mint="MintA", timestamp=995.0),
                self.evidence_row(mint="MintA", timestamp=996.0),
            ],
            market_provider=provider,
            execute=True,
            generated_at=1000.0,
            max_event_snapshot_lag_seconds=10,
        )

        self.assertEqual(provider.calls, ["MintA"])
        self.assertEqual(report["summary"]["unique_mints_selected"], 1)
        self.assertEqual(report["summary"]["snapshots_collected"], 1)
        self.assertEqual(report["summary"]["evidence_rows_with_forward_context"], 2)
        first_row = report["evidence_records"][0]
        context = first_row["estimated_entry_context"]
        self.assertEqual(context["price"], 0.01)
        self.assertEqual(context["liquidity"], 25_000)
        self.assertEqual(context["market_cap"], 100_000)
        self.assertEqual(context["source"], "forward_market_context:dexscreener")
        self.assertEqual(context["snapshot_time"], 1000.0)
        self.assertEqual(context["snapshot_lag_seconds"], 5.0)
        self.assertTrue(context["decision_time_safe"])
        self.assertTrue(context["forward_capture"])
        self.assertNotIn("entry_price", first_row["missing_fields"])
        snapshot = report["market_context_snapshots"][0]
        self.assertEqual(snapshot["mint"], "MintA")
        self.assertEqual(snapshot["price"], 0.01)
        self.assertEqual(snapshot["payload"]["market_cap"], 100_000)

    def test_dry_run_does_not_call_market_provider(self):
        provider = FakeMarketProvider()
        report = build_forward_market_context_report(
            evidence_records=[self.evidence_row()],
            market_provider=provider,
            execute=False,
            generated_at=1000.0,
        )

        self.assertEqual(provider.calls, [])
        self.assertEqual(report["summary"]["dry_run_mints"], 1)
        self.assertEqual(report["summary"]["snapshots_collected"], 0)
        self.assertEqual(report["evidence_records"][0]["estimated_entry_context"]["price"], None)

    def test_stale_snapshot_is_preserved_but_not_used_as_entry_context(self):
        provider = FakeMarketProvider()
        report = build_forward_market_context_report(
            evidence_records=[self.evidence_row(timestamp=100.0)],
            market_provider=provider,
            execute=True,
            generated_at=1000.0,
            max_event_snapshot_lag_seconds=30,
        )

        row = report["evidence_records"][0]
        self.assertEqual(report["summary"]["snapshots_collected"], 1)
        self.assertEqual(report["summary"]["evidence_rows_stale_for_context"], 1)
        self.assertEqual(row["estimated_entry_context"]["price"], None)
        self.assertIn("market_context_snapshot_stale_for_event", row["risk_flags"])

    def test_blocks_execute_when_market_context_budget_exceeds_limit(self):
        provider = FakeMarketProvider()
        report = build_forward_market_context_report(
            evidence_records=[self.evidence_row(mint=f"Mint{i}") for i in range(3)],
            market_provider=provider,
            execute=True,
            generated_at=1000.0,
            max_market_context_calls_per_cycle=2,
        )

        self.assertEqual(provider.calls, [])
        self.assertEqual(report["summary"]["mints_blocked_api_budget"], 3)
        self.assertEqual(report["api_budget"]["budget_status"], "blocked_market_context_cycle_limit")
        self.assertFalse(report["api_budget"]["execute_allowed"])

    def test_dexscreener_fetch_sends_browser_user_agent(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return (
                    b'{"pairs":[{"chainId":"solana","dexId":"pumpswap","url":"https://dexscreener.test/MintA",'
                    b'"pairAddress":"PairA","priceUsd":"0.01","marketCap":100000,"fdv":100000,'
                    b'"liquidity":{"usd":25000},"txns":{"m5":{"buys":7,"sells":5}}}]}'
                )

        def fake_urlopen(request, timeout):
            self.assertIn("Mozilla", request.get_header("User-agent") or "")
            return FakeResponse()

        with patch("wallets.forward_market_context.urlopen", fake_urlopen):
            info = fetch_dexscreener_market_info("MintA")

        self.assertEqual(info["source"], "dexscreener")
        self.assertEqual(info["market_cap"], 100000)
        self.assertEqual(info["tx_count_m5"], 12)


if __name__ == "__main__":
    unittest.main()
