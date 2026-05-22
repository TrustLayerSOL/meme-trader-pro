import tempfile
import unittest
from pathlib import Path

from core.rpc_provider import HeliusRpcProvider
from utils.build_forward_free_rpc_provider_rotation import write_forward_free_rpc_provider_rotation_report
from wallets.forward_free_rpc_provider_rotation import build_forward_free_rpc_provider_rotation_report
from wallets.forward_free_rpc_provider_rotation import recommend_provider_rotation


def fake_probe_factory(results):
    calls = []

    def fake_probe(provider):
        calls.append(provider.url)
        return dict(results[provider.url])

    fake_probe.calls = calls
    return fake_probe


class ForwardFreeRpcProviderRotationTests(unittest.TestCase):
    def test_rotation_filters_paid_urls_and_ranks_healthy_public_provider_first(self):
        fake_probe = fake_probe_factory({
            "https://api.mainnet-beta.solana.com": {
                "ok": False,
                "error": "rate limit",
                "latency_ms": 900,
            },
            "https://solana-rpc.publicnode.com": {
                "ok": True,
                "slot": 123,
                "latency_ms": 120,
            },
        })

        report = build_forward_free_rpc_provider_rotation_report(
            free_rpc_urls=(
                "https://solana-rpc.publicnode.com,"
                "https://mainnet.helius-rpc.com/?api-key=SECRET"
            ),
            probe=fake_probe,
            generated_at=1_700_000_000,
        )

        self.assertEqual(report["mode"], "FORWARD_FREE_RPC_PROVIDER_ROTATION_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["paid_rpc_allowed"])
        self.assertEqual(report["wallet_list_mutations"], 0)
        self.assertEqual(report["trust_mutations"], 0)
        self.assertEqual(report["providers_tested"], 2)
        self.assertEqual(report["healthy_providers"], 1)
        self.assertEqual(report["offline_providers"], 1)
        self.assertEqual(report["recommendation"], "USE_HEALTHY_FREE_PROVIDER")
        self.assertEqual(report["recommended_free_rpc_urls"], ["https://solana-rpc.publicnode.com"])
        self.assertEqual(fake_probe.calls, [
            "https://api.mainnet-beta.solana.com",
            "https://solana-rpc.publicnode.com",
        ])
        self.assertNotIn("SECRET", str(report))

    def test_rotation_reports_no_usable_provider_when_all_fail(self):
        fake_probe = fake_probe_factory({
            "https://api.mainnet-beta.solana.com": {"ok": False, "error": "429", "latency_ms": 50},
            "https://example.invalid": {"ok": False, "error": "timeout", "latency_ms": 8000},
        })

        report = build_forward_free_rpc_provider_rotation_report(
            free_rpc_urls="https://example.invalid",
            probe=fake_probe,
        )

        self.assertEqual(report["healthy_providers"], 0)
        self.assertEqual(report["recommendation"], "NO_USABLE_FREE_PROVIDER")
        self.assertEqual(report["recommended_free_rpc_urls"], [])
        self.assertIn("no_healthy_free_rpc_provider", report["blockers"])

    def test_recommendation_allows_degraded_small_only_for_slow_success(self):
        rows = [
            {
                "name": "slow_public",
                "ok": True,
                "status": "degraded",
                "url": "https://slow.example",
                "safe_url": "https://slow.example",
                "latency_ms": 2500,
            }
        ]

        recommendation, blockers = recommend_provider_rotation(rows)

        self.assertEqual(recommendation, "USE_DEGRADED_FREE_PROVIDER_SMALL_ONLY")
        self.assertEqual(blockers, ["free_rpc_latency_degraded"])

    def test_writer_persists_review_only_report(self):
        fake_probe = fake_probe_factory({
            "https://api.mainnet-beta.solana.com": {
                "ok": True,
                "slot": 456,
                "latency_ms": 50,
            },
        })

        with tempfile.TemporaryDirectory() as tmp:
            report = write_forward_free_rpc_provider_rotation_report(
                out_path=Path(tmp) / "rotation.json",
                free_rpc_urls="",
                probe=fake_probe,
                generated_at=1_700_000_001,
            )

            self.assertEqual(report["recommendation"], "USE_HEALTHY_FREE_PROVIDER")
            self.assertTrue(Path(tmp, "rotation.json").exists())
            self.assertEqual(len(list(Path(tmp).glob("forward_free_rpc_provider_rotation_*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
