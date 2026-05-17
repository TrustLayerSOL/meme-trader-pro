import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from research.wallet_ecosystem_intelligence import build_wallet_ecosystem_intelligence_report
from utils.build_wallet_ecosystem_intelligence import write_wallet_ecosystem_intelligence_report


def replay_scorecard():
    return {
        "mode": "WALLET_REPLAY_SCORECARD_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {"events": 5, "wallets": 4, "co_entry_pairs": 3},
        "ecosystems": {
            "top_co_entry_pairs": [
                {"wallets": ["WalletA", "WalletB"], "count": 3},
                {"wallets": ["WalletA", "WalletC"], "count": 2},
                {"wallets": ["WalletD", "WalletE"], "count": 1},
            ],
            "repeated_pair_count": 2,
        },
        "wallets": {
            "WalletA": {
                "total_events": 5,
                "fillable_events": 4,
                "windows": {"15m": {"known": 4, "runner": 3, "rug": 0}},
                "signal_quality": {
                    "known_rate_15m": 0.8,
                    "runner_rate_known_15m": 0.75,
                    "rug_rate_known_15m": 0.0,
                    "review_status": "reviewable",
                },
                "co_entry_partners": [{"wallet": "WalletB", "count": 3}, {"wallet": "WalletC", "count": 2}],
            },
            "WalletB": {
                "total_events": 3,
                "fillable_events": 3,
                "windows": {"15m": {"known": 3, "runner": 2, "rug": 0}},
                "signal_quality": {
                    "known_rate_15m": 1.0,
                    "runner_rate_known_15m": 0.667,
                    "rug_rate_known_15m": 0.0,
                    "review_status": "reviewable",
                },
                "co_entry_partners": [{"wallet": "WalletA", "count": 3}],
            },
            "WalletC": {
                "total_events": 2,
                "fillable_events": 1,
                "windows": {"15m": {"known": 1, "runner": 0, "rug": 1}},
                "signal_quality": {
                    "known_rate_15m": 0.5,
                    "runner_rate_known_15m": 0.0,
                    "rug_rate_known_15m": 1.0,
                    "review_status": "risk_review",
                },
                "co_entry_partners": [{"wallet": "WalletA", "count": 2}],
            },
            "WalletD": {
                "total_events": 1,
                "fillable_events": 1,
                "windows": {"15m": {"known": 1, "runner": 1, "rug": 0}},
                "signal_quality": {
                    "known_rate_15m": 1.0,
                    "runner_rate_known_15m": 1.0,
                    "rug_rate_known_15m": 0.0,
                    "review_status": "insufficient_replay_coverage",
                },
                "co_entry_partners": [{"wallet": "WalletE", "count": 1}],
            },
        },
    }


class WalletEcosystemIntelligenceTests(unittest.TestCase):
    def test_report_builds_review_only_stage5_graph(self):
        report = build_wallet_ecosystem_intelligence_report(replay_scorecard=replay_scorecard(), generated_at=123.0)

        self.assertEqual(report["mode"], "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertEqual(report["summary"]["stage5_wallet_ecosystem_completion_pct"], 100)
        self.assertEqual(report["summary"]["wallet_nodes"], 4)
        self.assertEqual(report["summary"]["co_entry_edges"], 3)
        self.assertEqual(report["summary"]["repeated_co_entry_edges"], 2)
        self.assertEqual(report["summary"]["cluster_candidates"], 1)
        self.assertEqual(report["relationship_source_status"]["co_entry"], "available_from_wallet_replay_scorecard")
        self.assertEqual(report["relationship_source_status"]["funding_overlap"], "blocked_missing_source")
        self.assertEqual(report["relationship_source_status"]["deployer_links"], "blocked_missing_source")
        self.assertIn("funding_overlap_source_missing", report["residual_data_blockers"])
        self.assertIn("deployer_link_source_missing", report["residual_data_blockers"])
        self.assertIn("wallet_nodes_indexed", report["passed_gates"])
        self.assertIn("trust_mutation_blocked", report["passed_gates"])

    def test_report_ranks_edges_and_cluster_candidates(self):
        report = build_wallet_ecosystem_intelligence_report(replay_scorecard=replay_scorecard(), generated_at=123.0)

        edge = report["co_entry_edges"][0]
        self.assertEqual(edge["wallets"], ["WalletA", "WalletB"])
        self.assertEqual(edge["count"], 3)
        self.assertEqual(edge["relationship_type"], "repeated_co_entry")
        self.assertEqual(edge["review_priority"], "high")

        cluster = report["cluster_candidates"][0]
        self.assertEqual(cluster["wallets"], ["WalletA", "WalletB", "WalletC"])
        self.assertEqual(cluster["repeated_edges"], 2)
        self.assertEqual(cluster["review_status"], "needs_ecosystem_review")

    def test_report_keeps_completion_incomplete_when_scorecard_missing(self):
        report = build_wallet_ecosystem_intelligence_report(replay_scorecard={}, generated_at=123.0)

        self.assertLess(report["summary"]["stage5_wallet_ecosystem_completion_pct"], 100)
        self.assertIn("scorecard_visible", report["failed_gates"])
        self.assertIn("co_entry_pairs_indexed", report["failed_gates"])
        self.assertTrue(report["live_execution_locked"])

    def test_writer_creates_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            scorecard_path = root / "wallet_replay_scorecard.json"
            out_path = root / "wallet_ecosystem_intelligence_report.json"
            scorecard_path.write_text(json.dumps(replay_scorecard()), encoding="utf-8")

            report = write_wallet_ecosystem_intelligence_report(
                replay_scorecard_path=scorecard_path,
                output_path=out_path,
                generated_at=123.0,
            )

            self.assertEqual(report["summary"]["stage5_wallet_ecosystem_completion_pct"], 100)
            self.assertEqual(report["input_paths"]["wallet_replay_scorecard"], str(scorecard_path))
            self.assertTrue(out_path.exists())
            saved = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["mode"], "WALLET_ECOSYSTEM_INTELLIGENCE_STAGE5_REVIEW_ONLY")

