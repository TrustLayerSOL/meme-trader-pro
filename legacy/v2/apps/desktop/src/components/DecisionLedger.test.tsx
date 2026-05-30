import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DecisionLedger } from "./DecisionLedger";
import type { DecisionLedgerPayload } from "../lib/decisions";

describe("DecisionLedger", () => {
  it("renders richer backend evidence in selected decision details", () => {
    const decisions: DecisionLedgerPayload = {
      live_execution_locked: true,
      count: 1,
      items: [
        {
          decision_id: "dec_rich",
          mint: "RichMint111111111111111111111111111111111",
          signal_type: "cluster",
          final_action: "skip",
          action_reason: "exit liquidity blocked",
          paper_lane: "main",
          total_score: 74,
          threshold: 68,
          risk_label: "WARNING",
          buy_quote_pass: true,
          sell_quote_pass: false,
          payload: {
            inputs: {
              wallets: ["WalletA111111111111111111111111111111"],
              social_match: { matched: true, reason: "ticker match" },
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
              risk: { warnings: ["sell route degraded"] },
              scoring: { reasons: ["score ok"] },
              holder_cluster: {
                holder_risk_label: "WARNING",
                holder_count: 41,
                top_10_pct: 72.2,
                linked_wallet_risk: { risk_label: "WATCH" },
              },
            },
            quotes: {
              buy: { reason: "quote_passed" },
              sell: { reason: "no_route_plan" },
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
        },
      ],
    };

    const markup = renderToStaticMarkup(<DecisionLedger decisions={decisions} loaded={true} onSelectMint={() => undefined} />);

    expect(markup).toContain("Catalyst Evidence");
    expect(markup).toContain("@alpha");
    expect(markup).toContain("Route Feasibility");
    expect(markup).toContain("Sell blocked: no_route_plan");
    expect(markup).toContain("Holder / Cluster");
    expect(markup).toContain("top 10 72.2%");
    expect(markup).toContain("Market Context");
    expect(markup).toContain("stablecoin ok");
    expect(markup).toContain("Paper Outcome");
    expect(markup).toContain("target_profit");
    expect(markup).toContain("OpenAI Advisory");
    expect(markup).toContain("Explain Decision");
    expect(markup).toContain("Advisory only");
  });
});
