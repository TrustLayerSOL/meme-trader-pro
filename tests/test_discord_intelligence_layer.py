import unittest

from research.discord_intelligence_layer import build_discord_intelligence_layer_report


def wallet_promotion_demotion():
    return {
        "mode": "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "stage4_promotion_demotion_completion_pct": 100,
            "promotion_review": 1,
            "demotion_review": 1,
            "remaining_blocked_wallets": 36,
            "trusted_promotions_allowed": 0,
            "auto_applied": 0,
        },
        "operator_alerts": [
            {
                "severity": "info",
                "code": "stage4_review_only_complete",
                "message": "Stage 4 is complete for review only.",
            }
        ],
    }


def behavioral_intelligence():
    return {
        "mode": "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "auto_trust_mutation_allowed": False,
        "behavioral_score_driving_allowed": False,
        "summary": {
            "stage9_behavioral_intelligence_completion_pct": 100,
            "pattern_candidates": 2,
            "dominant_regime": "unknown",
            "proof_readiness_pct": 0,
            "known_15m_outcomes": 2,
        },
        "behavioral_pattern_candidates": [
            {
                "pattern_id": "behavioral-cluster-001",
                "pattern_type": "repeated_co_entry_cluster",
                "wallet_count": 18,
                "repeated_edges": 17,
                "total_shared_events": 124,
                "ecosystem_review_priority": "high",
                "dominant_regime": "unknown",
                "proof_readiness_pct": 0,
                "pattern_status": "blocked_needs_evidence",
                "can_drive_wallet_trust": False,
                "wallets": ["WalletA", "WalletB", "WalletC"],
            },
            {
                "pattern_id": "behavioral-cluster-002",
                "pattern_type": "repeated_co_entry_cluster",
                "wallet_count": 2,
                "repeated_edges": 1,
                "total_shared_events": 3,
                "ecosystem_review_priority": "observe_more",
                "dominant_regime": "unknown",
                "proof_readiness_pct": 0,
                "pattern_status": "blocked_needs_evidence",
                "can_drive_wallet_trust": False,
                "wallets": ["WalletD", "WalletE"],
            },
        ],
    }


def behavioral_trust_validation():
    return {
        "mode": "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "behavioral_trust_changes_allowed": False,
        "summary": {
            "behavioral_validation_completion_pct": 100,
            "behavioral_trust_justified": False,
            "validated_patterns": 2,
            "trust_ready_patterns": 0,
            "proof_readiness_pct": 0,
            "known_15m_outcomes": 2,
            "known_15m_required": 30,
            "fillable_rate": 6,
            "fillable_rate_required": 70,
        },
        "blocked_data_issues": [
            "proof_readiness_below_threshold",
            "insufficient_known_outcome_density",
        ],
    }


def proof_readiness():
    return {
        "mode": "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "summary": {
            "blocker_reduction_completion_pct": 100,
            "proof_readiness_pct": 0,
            "known_15m_outcomes": 2,
            "known_15m_required": 30,
            "known_15m_needed": 28,
            "fillable_rate": 6,
            "fillable_rate_required": 70,
            "score_ready_market_context_records": 0,
            "missing_market_context_rows": 643,
        },
        "reduction_queue": [
            {
                "priority": 1,
                "category": "score_ready_market_context",
                "current": 0,
                "target": 1,
                "gap": 1,
                "next_action": "Recover decision-time supply/market-cap context.",
                "can_drive_wallet_trust": False,
            }
        ],
    }


def market_regime():
    return {
        "mode": "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY",
        "review_only": True,
        "live_execution_locked": True,
        "wallet_list_mutated": False,
        "regime_score_driving_allowed": False,
        "summary": {
            "stage7_regime_detection_completion_pct": 100,
            "regime_tags_observed": 1,
            "regime_data_readiness_pct": 0,
            "unknown_regime_events": 6042,
        },
        "regime_rows": [
            {
                "regime": "unknown",
                "events": 6042,
                "known_15m_outcomes": 2,
                "fillable_events": 353,
                "can_drive_wallet_trust": False,
            }
        ],
    }


class DiscordIntelligenceLayerTests(unittest.TestCase):
    def test_report_builds_sparse_high_signal_events_with_replay_limits(self):
        report = build_discord_intelligence_layer_report(
            wallet_promotion_demotion=wallet_promotion_demotion(),
            behavioral_intelligence=behavioral_intelligence(),
            behavioral_trust_validation=behavioral_trust_validation(),
            proof_readiness_blocker_reduction=proof_readiness(),
            market_regime_detection=market_regime(),
            generated_at=123.0,
        )

        self.assertEqual(report["mode"], "DISCORD_BEHAVIORAL_INTELLIGENCE_REVIEW_ONLY")
        self.assertTrue(report["review_only"])
        self.assertTrue(report["live_execution_locked"])
        self.assertFalse(report["wallet_list_apply_allowed"])
        self.assertFalse(report["wallet_list_mutated"])
        self.assertFalse(report["auto_trust_mutation_allowed"])
        self.assertFalse(report["discord_dispatch_enabled"])
        self.assertEqual(report["summary"]["discord_intelligence_layer_completion_pct"], 100)
        self.assertLessEqual(report["summary"]["events_prepared"], 6)
        self.assertGreaterEqual(report["summary"]["events_prepared"], 3)
        self.assertEqual(report["summary"]["raw_wallet_events_suppressed"], 3)

        channels = {event["channel"] for event in report["discord_events"]}
        self.assertIn("#behavioral-patterns", channels)
        self.assertIn("#replay-validation", channels)
        self.assertIn("#research-updates", channels)
        for event in report["discord_events"]:
            self.assertFalse(event["can_drive_trade"])
            self.assertFalse(event["can_mutate_wallet_trust"])
            self.assertIn("Proof readiness", event["message"])
            self.assertIn("Live execution remains locked", event["message"])

    def test_no_high_signal_events_when_inputs_have_no_state_change(self):
        report = build_discord_intelligence_layer_report(
            wallet_promotion_demotion={
                "mode": "WALLET_PROMOTION_DEMOTION_SYSTEM_REVIEW_ONLY",
                "review_only": True,
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"stage4_promotion_demotion_completion_pct": 100},
            },
            behavioral_intelligence={
                "mode": "BEHAVIORAL_INTELLIGENCE_STAGE9_REVIEW_ONLY",
                "review_only": True,
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"stage9_behavioral_intelligence_completion_pct": 100},
                "behavioral_pattern_candidates": [],
            },
            behavioral_trust_validation={
                "mode": "BEHAVIORAL_TRUST_VALIDATION_REVIEW_ONLY",
                "review_only": True,
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"behavioral_validation_completion_pct": 100, "behavioral_trust_justified": False},
            },
            proof_readiness_blocker_reduction={
                "mode": "PROOF_READINESS_BLOCKER_REDUCTION_REVIEW_ONLY",
                "review_only": True,
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"blocker_reduction_completion_pct": 100},
                "reduction_queue": [],
            },
            market_regime_detection={
                "mode": "MARKET_REGIME_DETECTION_STAGE7_REVIEW_ONLY",
                "review_only": True,
                "live_execution_locked": True,
                "wallet_list_mutated": False,
                "summary": {"stage7_regime_detection_completion_pct": 100},
                "regime_rows": [],
            },
            generated_at=123.0,
        )

        self.assertEqual(report["summary"]["events_prepared"], 0)
        self.assertEqual(report["discord_events"], [])
        self.assertIn("high_signal_events_only", report["passed_gates"])

