import json
import tempfile
import unittest
from pathlib import Path

from analysis.rejection_logger import record_rejection
from analysis.trade_classifier import classify_closed_trade
from analysis.trade_postmortem import (
    append_postmortem_jsonl,
    build_postmortem_record,
    load_postmortem_ids,
)


class AnalysisPostmortemTests(unittest.TestCase):
    def test_hard_stop_loser_classification(self):
        trade = {
            "mint": "SoMeMint111",
            "status": "closed",
            "entry_price": 1.0,
            "exit_reason": "hard_stop_loss",
            "total_pnl": -10,
            "sells": [],
        }
        tags, aux = classify_closed_trade(trade, {})
        self.assertIn("loser", tags)
        self.assertIn("stop-loss exit", tags)
        self.assertEqual((aux["exit_detail"] or {}).get("primary_exit_attribution"), "emergency exit")

    def test_take_profit_winner_classification(self):
        trade = {
            "mint": "SoMeMint222",
            "status": "closed",
            "entry_price": 1.0,
            "quoted_entry_price": 1.0,
            "close_price": 2.5,
            "exit_reason": "take_profit_2.5x",
            "total_pnl": 15,
            "wallets": ["W1"],
            "sells": [
                {"reason": "take_profit_2.5x", "net_proceeds": 10},
            ],
        }
        tags, aux = classify_closed_trade(trade, {})
        self.assertIn("winner", tags)
        self.assertIn("take-profit exit", tags)
        self.assertEqual((aux["exit_detail"] or {}).get("primary_exit_attribution"), "fixed TP")

    def test_postmortem_record_shape(self):
        trade = {
            "mint": "M",
            "token_mint": "M",
            "status": "closed",
            "close_time": 100.0,
            "entry_time": 99.0,
            "entry_reason": "test",
            "exit_reason": "hard_stop_loss",
            "total_pnl": -1,
            "liquidity_usd": 250_000,
            "signal_metadata": {"decision_id": "dec_x"},
            "wallets": [],
            "sells": [],
        }
        rec = build_postmortem_record(trade, {"holder_concentration_risk": None})
        self.assertEqual(rec["decision_id"], "dec_x")
        self.assertIn("tracked", rec)
        self.assertIn("classifications", rec)
        self.assertIn("entry reason", rec["tracked"])
        self.assertIn("liquidity at entry", rec["tracked"])

    def test_jsonl_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            fp = Path(tmp) / "pm.jsonl"
            trade = {
                "mint": "MZ",
                "token_mint": "MZ",
                "status": "closed",
                "close_time": 200.0,
                "entry_time": 190.0,
                "exit_reason": "timeout",
                "total_pnl": 0,
                "wallets": [],
                "sells": [],
                "entry_reason": "e",
            }
            rec = build_postmortem_record(trade, {})
            append_postmortem_jsonl(rec, fp)
            ids = load_postmortem_ids(fp)
            self.assertEqual(len(ids), 1)

    def test_hints_from_stored_payload_maps_holder_regime(self):
        from analysis.decision_lookup import hints_from_stored_payload

        inner = {
            "rule_outcomes": {"holder_cluster": {"holder_risk_label": "DANGER", "holder_reasons": ["x"]}},
            "inputs": {"market_context": {"risk_regime": "volatile"}},
        }
        h = hints_from_stored_payload(inner)
        self.assertEqual(h["holder_risk_label"], "DANGER")
        self.assertEqual(h["market_risk_regime"], "volatile")

    def test_rejection_record_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rej.jsonl"
            record_rejection(
                "liquidity too low",
                {"mint": "M1"},
                hypothetical_outcome_if_traded=None,
                path=path,
            )
            txt = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(txt), 1)
            row = json.loads(txt[0])
            self.assertEqual(row["rejection reason"], "liquidity too low")
            self.assertIn("signal context", row)
            self.assertEqual(row["what would have happened afterward if traded"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
