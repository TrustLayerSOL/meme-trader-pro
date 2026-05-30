import unittest
from unittest.mock import patch

from analysis import rejection_hooks


class PickScannerRejectionReasonTests(unittest.TestCase):
    def test_hard_block_reason_wins_over_last_scoring_line(self):
        r = rejection_hooks._pick_scanner_rejection_reason(
            {"should_trade": False, "reasons": ["market_radar_skip: low", "tail"]},
            {"hard_block": True, "hard_block_reason": "liquidity_rug_signal"},
        )
        self.assertEqual(r, "liquidity_rug_signal")

    def test_first_priority_line_in_document_order(self):
        r = rejection_hooks._pick_scanner_rejection_reason(
            {
                "should_trade": False,
                "reasons": [
                    "BLOCK: thin pool",
                    "market_radar_skip: noise",
                ],
            },
            {},
        )
        self.assertEqual(r, "BLOCK: thin pool")

    def test_unknown_skip_when_empty(self):
        r = rejection_hooks._pick_scanner_rejection_reason({"should_trade": False, "reasons": []}, {})
        self.assertEqual(r, "unknown_skip")


class MaybeLogScannerStrategySkipTests(unittest.TestCase):
    def test_logs_ranked_reason_via_record_rejection(self):
        payload = {"mint": "MintX", "type": "cluster"}
        decision = {
            "should_trade": False,
            "paper_lane": "main",
            "reasons": [
                "BLOCK: first match",
                "market_radar_skip: later",
            ],
        }
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_strategy_skip(
                payload,
                decision,
                decision_id="dec-1",
                settings={"analysis_rejection_log_enabled": True},
            )
        rec.assert_called_once()
        args, kwargs = rec.call_args
        self.assertEqual(args[0], "BLOCK: first match")
        self.assertEqual(kwargs.get("source"), "scanner")
        self.assertEqual(kwargs.get("decision_id"), "dec-1")

    def test_no_log_when_should_trade(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_strategy_skip(
                {"mint": "m"},
                {"should_trade": True, "reasons": ["BLOCK: x"]},
                decision_id=None,
                settings={"analysis_rejection_log_enabled": True},
            )
        rec.assert_not_called()

    def test_no_log_when_disabled(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_strategy_skip(
                {"mint": "m"},
                {"should_trade": False, "reasons": ["BLOCK: x"]},
                decision_id=None,
                settings={"analysis_rejection_log_enabled": False},
            )
        rec.assert_not_called()


class MaybeLogScannerRuntimeSkipTests(unittest.TestCase):
    def test_logs_explicit_reason_and_source(self):
        decision = {"paper_lane": "paper_a", "score": 40.0, "threshold": 68.0}
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_runtime_skip(
                mint="MintRT",
                decision_id="dec-rt",
                reason="pre_filter_age",
                decision=decision,
                settings={"analysis_rejection_log_enabled": True},
            )
        rec.assert_called_once()
        args, kwargs = rec.call_args
        self.assertEqual(args[0], "pre_filter_age")
        self.assertEqual(kwargs.get("source"), "scanner_runtime")
        self.assertEqual(kwargs.get("lane"), "paper_a")
        self.assertEqual(kwargs.get("decision_id"), "dec-rt")
        ctx = args[1]
        self.assertTrue(ctx.get("runtime_skip"))
        self.assertEqual(ctx.get("score"), 40.0)
        self.assertEqual(ctx.get("mint"), "MintRT")

    def test_extra_merges_into_context(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_runtime_skip(
                mint="m",
                decision_id=None,
                reason="r",
                decision={"paper_lane": "main"},
                settings={"analysis_rejection_log_enabled": True},
                extra={"edge_score": 12, "stage": "early"},
            )
        ctx = rec.call_args[0][1]
        self.assertEqual(ctx.get("edge_score"), 12)
        self.assertEqual(ctx.get("stage"), "early")

    def test_no_log_when_disabled(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_scanner_runtime_skip(
                mint="m",
                decision_id=None,
                reason="r",
                decision={},
                settings={"analysis_rejection_log_enabled": False},
            )
        rec.assert_not_called()


class MaybeLogMarketRadarSkipTests(unittest.TestCase):
    def test_uses_skip_reason_and_defaults(self):
        payload = {
            "mint": "MR1",
            "type": "market_radar_hot",
            "paper_lane": "mr_lane",
            "total_score": 50.0,
            "score_threshold": 60.0,
            "score_reasons": ["a", "b", "c"],
        }
        summary = {"skip_reason": "low_volume_bucket", "skip_bucket": "score_gate"}
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_market_radar_skip(
                payload,
                summary,
                decision_id="dec-mr",
                settings={"analysis_rejection_log_enabled": True},
            )
        args, kwargs = rec.call_args
        self.assertEqual(args[0], "low_volume_bucket")
        self.assertEqual(kwargs.get("source"), "market_radar")
        self.assertEqual(kwargs.get("lane"), "mr_lane")
        ctx = args[1]
        self.assertEqual(ctx.get("skip_bucket"), "score_gate")
        self.assertEqual(ctx.get("signal_type"), "market_radar_hot")
        self.assertEqual(ctx.get("score_reasons_tail"), ["a", "b", "c"])

    def test_default_reason_when_no_skip_reason(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_market_radar_skip(
                {"mint": "m"},
                {},
                decision_id=None,
                settings={"analysis_rejection_log_enabled": True},
            )
        self.assertEqual(rec.call_args[0][0], "market_radar_skip")

    def test_no_log_when_disabled(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_market_radar_skip(
                {"mint": "m"},
                {"skip_reason": "x"},
                None,
                {"analysis_rejection_log_enabled": False},
            )
        rec.assert_not_called()


class MaybeLogMarketRadarRuntimeSkipTests(unittest.TestCase):
    def test_logs_reason_and_runtime_source(self):
        payload = {
            "mint": "MRT",
            "market_info": {"liquidity": 1000.0, "market_cap": 1e6, "price": 0.1},
        }
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_market_radar_runtime_skip(
                payload,
                decision_id="id-99",
                reason="stale_quote",
                settings={"analysis_rejection_log_enabled": True},
            )
        args, kwargs = rec.call_args
        self.assertEqual(args[0], "stale_quote")
        self.assertEqual(kwargs.get("source"), "market_radar_runtime")
        self.assertEqual(kwargs.get("lane"), "market_radar")
        ctx = args[1]
        self.assertEqual(ctx.get("skip_bucket"), "runtime_precheck")
        self.assertEqual(ctx.get("mint"), "MRT")
        self.assertEqual(ctx.get("market_info", {}).get("liquidity"), 1000.0)

    def test_no_log_when_disabled(self):
        with patch("analysis.rejection_logger.record_rejection") as rec:
            rejection_hooks.maybe_log_market_radar_runtime_skip(
                {"mint": "m"},
                None,
                "r",
                {"analysis_rejection_log_enabled": False},
            )
        rec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
