import { describe, expect, it } from "vitest";
import {
  decisionMarketSummary,
  decisionMatchesFilter,
  decisionOutcomeSummary,
  decisionQuoteDetail,
  decisionQuotePair,
  decisionRiskDetail,
  decisionWalletSummary,
  selectedDecisionForFilter,
  type DecisionRecord,
} from "./decisions";

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

    const radarLane = { ...baseDecision, decision_id: "dec_radar_lane", paper_lane: "market_radar" as const };
    const radarPayload = {
      ...baseDecision,
      decision_id: "dec_radar_payload",
      paper_lane: "exploration",
      payload: {
        ...baseDecision.payload,
        market_radar: { decision: { skip_reason: "thin" } },
      },
    };
    expect(decisionMatchesFilter(radarLane, "co_main")).toBe(true);
    expect(decisionMatchesFilter(radarLane, "market_radar")).toBe(true);
    expect(decisionMatchesFilter(radarPayload, "market_radar")).toBe(true);
    expect(decisionMatchesFilter(baseDecision, "market_radar")).toBe(false);
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

  it("formats richer quote, risk, market, and outcome drilldowns", () => {
    const richDecision: DecisionRecord = {
      ...baseDecision,
      position_size_usd: 25,
      trade_status: "closed",
      pnl: 42.5,
      pnl_pct: 170,
      result: { exit_reason: "trailing_stop" },
      payload: {
        ...baseDecision.payload,
        inputs: {
          ...baseDecision.payload?.inputs,
          market_info: { market_cap: 153000, liquidity: 32700, holders: 656, tx_count: 1401 },
          token_inspection: { risk_label: "PASS", reasons: ["No dangerous token mechanics detected"] },
        },
        rule_outcomes: {
          ...baseDecision.payload?.rule_outcomes,
          risk: {
            hard_block: false,
            warnings: ["Top holder controls at least 20%"],
            holder_concentration: { risk_label: "WARNING", metrics: { holder_count: 44, top_1_pct: 21.2 } },
          },
        },
        quotes: {
          buy: { reason: "quote_ok", route: "Jupiter", price_impact_pct: 1.4 },
          sell: { reason: "sell_quote_ok", route: "Jupiter", price_impact_pct: 1.8 },
        },
      },
    };

    expect(decisionQuoteDetail(richDecision, "buy")).toContain("quote_ok");
    expect(decisionQuoteDetail(richDecision, "buy")).toContain("route Jupiter");
    expect(decisionQuoteDetail(richDecision, "buy")).toContain("impact 1.4%");
    expect(decisionRiskDetail(richDecision)).toContain("Token mechanics PASS");
    expect(decisionRiskDetail(richDecision)).toContain("Holder concentration WARNING");
    expect(decisionMarketSummary(richDecision)).toBe("MC $153K | Liq $32.7K | Holders 656 | Tx 1401");
    expect(decisionOutcomeSummary(richDecision)).toBe("closed | PnL $42.50 / 170% | exit trailing_stop");
  });
});
