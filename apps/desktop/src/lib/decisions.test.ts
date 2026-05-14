import { describe, expect, it } from "vitest";
import {
  decisionCatalystEvidenceSummary,
  decisionHolderClusterSummary,
  decisionMarketContextSummary,
  decisionMarketRadarSummary,
  decisionMatchesFilter,
  decisionPaperOutcomeSummary,
  decisionQuotePair,
  decisionRouteFeasibilitySummary,
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
    expect(decisionMatchesFilter({ ...baseDecision, paper_lane: "market_radar" }, "market_radar")).toBe(true);
    expect(decisionMatchesFilter({ ...baseDecision, paper_lane: "market_radar" }, "co_main")).toBe(true);
    expect(decisionMatchesFilter({ ...baseDecision, paper_lane: "main" }, "co_main")).toBe(true);
    expect(decisionMatchesFilter({ ...baseDecision, paper_lane: "exploration" }, "co_main")).toBe(false);
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

  it("formats richer backend evidence for decision detail drilldowns", () => {
    const richDecision: DecisionRecord = {
      ...baseDecision,
      payload: {
        ...baseDecision.payload,
        inputs: {
          ...baseDecision.payload?.inputs,
          social_catalyst: {
            matched: true,
            account: "alpha",
            keywords: ["launch"],
            event_ids: ["social_1"],
            catalyst_card_ids: ["card_1"],
            match_confidence: 0.91,
          },
          market_context: {
            risk_regime: "risk_off",
            sol_price_change_pct: -3.2,
            stablecoin: { usdc_depeg_warning: false },
          },
        },
        rule_outcomes: {
          ...baseDecision.payload?.rule_outcomes,
          holder_cluster: {
            holder_risk_label: "WARNING",
            holder_count: 41,
            top_10_pct: 72.2,
            linked_wallet_risk: { risk_label: "WATCH" },
          },
        },
        route_feasibility: {
          buy: { pass: true, reason: "quote_passed", route_count: 2, price_impact_pct: 1.2, slippage_bps: 1500 },
          sell: { pass: false, reason: "no_route_plan", route_count: 0, slippage_bps: 2000 },
        },
      },
      result: {
        trade_status: "closed",
        pnl_pct: 74,
        exit_reason: "target_profit",
        paper_outcome: {
          paper_lane: "exploration",
          entry_price: 0.001,
          exit_price: 0.0018,
          position_size_usd: 25,
          fees_usd: 0.18,
        },
      },
    };

    expect(decisionRouteFeasibilitySummary(richDecision)).toBe("Buy pass: quote_passed, routes 2, impact 1.2%, slip 1500bps | Sell blocked: no_route_plan, routes 0, slip 2000bps");
    expect(decisionHolderClusterSummary(richDecision)).toBe("WARNING | holders 41 | top 10 72.2% | linked WATCH");
    expect(decisionCatalystEvidenceSummary(richDecision)).toBe("matched | @alpha | keywords launch | 1 event | 1 card | confidence 0.91");
    expect(decisionMarketContextSummary(richDecision)).toBe("risk_off | SOL -3.2% | stablecoin ok");
    expect(decisionPaperOutcomeSummary(richDecision)).toBe("closed | exploration | PnL 74% | entry 0.001 | exit 0.0018 | size $25 | fees $0.18 | target_profit");
  });

  it("formats Market Radar skip and open reasons", () => {
    const radarDecision: DecisionRecord = {
      ...baseDecision,
      paper_lane: "market_radar",
      payload: {
        ...baseDecision.payload,
        market_radar: {
          decision: {
            skip_reason: "shared_quote_cooldown_after_429",
            skip_bucket: "quote_or_route",
            quote_retryable: true,
          },
        },
      },
    };

    expect(decisionMarketRadarSummary(radarDecision)).toBe("skip shared_quote_cooldown_after_429 | quote_or_route | retry soon");
  });
});
