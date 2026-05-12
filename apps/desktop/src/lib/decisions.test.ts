import { describe, expect, it } from "vitest";
import { decisionMatchesFilter, decisionQuotePair, decisionWalletSummary, selectedDecisionForFilter, type DecisionRecord } from "./decisions";

const baseDecision: DecisionRecord = {
  decision_id: "dec_base",
  mint: "BaseMint111111111111111111111111111111111",
  final_action: "skip_low_score",
  paper_lane: "main",
  total_score: 41,
  threshold: 70,
  risk_label: "OK",
  buy_quote_pass: true,
  sell_quote_pass: true,
  action_reason: "below_threshold",
  payload: {
    inputs: {
      wallets: ["WalletA111111111111111111111111111111"],
      social_match: { matched: false },
    },
    rule_outcomes: {
      risk: { hard_block: false, warnings: ["low liquidity"] },
      scoring: { reasons: ["wallet score below threshold"] },
    },
    quotes: {
      buy: { reason: "quote_ok" },
      sell: { reason: "sell_quote_ok" },
    },
  },
};

describe("decision ledger helpers", () => {
  it("matches the static Replay decision filters", () => {
    const bought = { ...baseDecision, decision_id: "dec_bought", final_action: "paper_opened" };
    const quoteFailed = { ...baseDecision, decision_id: "dec_quote", buy_quote_pass: false };
    const hardRisk = {
      ...baseDecision,
      decision_id: "dec_risk",
      risk_label: "DANGER",
      payload: { ...baseDecision.payload, rule_outcomes: { risk: { hard_block: true } } },
    };
    const social = {
      ...baseDecision,
      decision_id: "dec_social",
      payload: { ...baseDecision.payload, inputs: { social_match: { matched: true, reason: "mint match" } } },
    };

    expect(decisionMatchesFilter(bought, "bought")).toBe(true);
    expect(decisionMatchesFilter(baseDecision, "skipped")).toBe(true);
    expect(decisionMatchesFilter(quoteFailed, "quote_failed")).toBe(true);
    expect(decisionMatchesFilter(hardRisk, "hard_risk")).toBe(true);
    expect(decisionMatchesFilter(social, "social")).toBe(true);
    expect(decisionMatchesFilter(baseDecision, "wallet")).toBe(true);
  });

  it("keeps selected decision valid when filters change", () => {
    const rows = [
      { ...baseDecision, decision_id: "dec_skip", final_action: "skip_low_score" },
      { ...baseDecision, decision_id: "dec_quote", buy_quote_pass: false, final_action: "skip_quote_failed" },
    ];

    expect(selectedDecisionForFilter(rows, "dec_skip", "quote_failed")?.decision_id).toBe("dec_quote");
    expect(selectedDecisionForFilter(rows, "dec_quote", "quote_failed")?.decision_id).toBe("dec_quote");
    expect(selectedDecisionForFilter(rows, "missing", "hard_risk")).toBeNull();
  });

  it("formats quote and wallet summaries for detail drilldowns", () => {
    const quoteFailed = { ...baseDecision, buy_quote_pass: false, sell_quote_pass: null };

    expect(decisionQuotePair(quoteFailed)).toBe("B-/S?");
    expect(decisionWalletSummary(baseDecision)).toBe("WalletA1...1111");
  });
});
