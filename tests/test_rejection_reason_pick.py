import unittest

from analysis.rejection_reason_pick import pick_ranked_rejection_reason


class RejectionReasonPickTests(unittest.TestCase):
    def test_hard_block_reason_wins(self):
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason="something_else",
                scoring_reasons=["BLOCK: first", "other"],
                hard_block=True,
                hard_block_reason="  Rug pull guard  ",
                default="x",
            ),
            "Rug pull guard",
        )

    def test_informative_action_reason_before_scoring(self):
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason="pre_score_band_skip",
                scoring_reasons=["BLOCK: would win if action weak"],
                hard_block=False,
                hard_block_reason=None,
                default="d",
            ),
            "pre_score_band_skip",
        )

    def test_first_priority_line_in_document_order(self):
        reasons = [
            "market_radar_skip: low",
            "BLOCK: thin liquidity",
        ]
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason="sqlite_should_trade_false",
                scoring_reasons=reasons,
                hard_block=False,
                hard_block_reason=None,
                default="d",
            ),
            "market_radar_skip: low",
        )

        reasons2 = [
            "BLOCK: thin liquidity",
            "market_radar_skip: low score",
        ]
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason=None,
                scoring_reasons=reasons2,
                hard_block=False,
                hard_block_reason=None,
                default="d",
            ),
            "BLOCK: thin liquidity",
        )

    def test_fallback_last_line_then_default(self):
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason="sqlite_should_trade_false",
                scoring_reasons=["no needle one", "no needle two"],
                hard_block=False,
                hard_block_reason=None,
                default="fallback_default",
            ),
            "no needle two",
        )
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason="sqlite_should_trade_false",
                scoring_reasons=[],
                hard_block=False,
                hard_block_reason=None,
                default="fallback_default",
            ),
            "fallback_default",
        )

    def test_hard_block_without_reason_falls_through(self):
        self.assertEqual(
            pick_ranked_rejection_reason(
                action_reason=None,
                scoring_reasons=["BLOCK: x"],
                hard_block=True,
                hard_block_reason=None,
                default="d",
            ),
            "BLOCK: x",
        )


if __name__ == "__main__":
    unittest.main()
