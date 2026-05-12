import { describe, expect, it } from "vitest";
import { findTradeForMint, summarizeTrades, tradeLedgerSourceLabel, tradeMarketCapIn, tradeMarketCapOut, tradePnl, tradePnlPct, tradeReason } from "./trades";

describe("trade helpers", () => {
  it("finds trades by either mint key", () => {
    const trade = { token_mint: "abc", status: "open" };

    expect(findTradeForMint({ open_trades: [trade], closed_trades: [], failed_trades: [] }, "abc")).toBe(trade);
  });

  it("prioritizes exit lifecycle reasons", () => {
    expect(tradeReason({ entry_reason: "entry", close_reason: "closed" })).toBe("closed");
    expect(tradeReason({ reason: "scanner reason" })).toBe("scanner reason");
  });

  it("normalizes pnl percent", () => {
    expect(tradePnlPct({ total_pnl_pct: -12.5 })).toBe(-12.5);
    expect(tradePnlPct({})).toBeNull();
  });

  it("normalizes dollar pnl from common trade fields", () => {
    expect(tradePnl({ total_pnl: 4.25 })).toBe(4.25);
    expect(tradePnl({ pnl: -1.5 })).toBe(-1.5);
    expect(tradePnl({ realized_pnl: 2.75 })).toBe(2.75);
    expect(tradePnl({ unrealized_pnl: -0.25 })).toBe(-0.25);
    expect(tradePnl({ total_pnl: "bad" as unknown as number })).toBe(0);
  });

  it("summarizes open, closed, failed, and total pnl", () => {
    const summary = summarizeTrades({
      source: "paper_trades_json",
      open_trades: [{ total_pnl: 2 }, { unrealized_pnl: -0.5 }],
      closed_trades: [{ pnl: 4 }, { realized_pnl: -1 }],
      failed_trades: [{ failure_reason: "quote failed" }],
    });

    expect(summary.openCount).toBe(2);
    expect(summary.closedCount).toBe(2);
    expect(summary.failedCount).toBe(1);
    expect(summary.openPnl).toBe(1.5);
    expect(summary.closedPnl).toBe(3);
    expect(summary.totalPnl).toBe(4.5);
  });

  it("formats the declared trade ledger source", () => {
    expect(tradeLedgerSourceLabel({
      source: "paper_trades_json",
      source_detail: "data/paper_trades.json",
      open_trades: [],
      closed_trades: [],
      failed_trades: [],
    })).toBe("paper_trades_json | data/paper_trades.json");
    expect(tradeLedgerSourceLabel(null)).toBe("loading source");
  });

  it("normalizes entry and exit market caps for trade detail", () => {
    expect(tradeMarketCapIn({ entry_market_cap: 5000, market_cap_at_entry: 4500 })).toBe(5000);
    expect(tradeMarketCapIn({ market_cap_at_entry: 4500 })).toBe(4500);
    expect(tradeMarketCapOut({ exit_market_cap: 12000, current_market_cap: 9000 })).toBe(12000);
    expect(tradeMarketCapOut({ current_market_cap: 9000 })).toBe(9000);
    expect(tradeMarketCapOut({ market_cap: 8000 })).toBe(8000);
  });
});
