import type { TradeRecord, TradesPayload } from "./api";

export function tradeMint(trade: TradeRecord): string {
  return trade.token_mint || trade.mint || "";
}

export function findTradeForMint(trades: TradesPayload | null, mint: string): TradeRecord | null {
  if (!trades || !mint) return null;
  return [...trades.open_trades, ...trades.closed_trades, ...trades.failed_trades].find((trade) => tradeMint(trade) === mint) || null;
}

export function tradeLabel(trade: TradeRecord): string {
  return trade.symbol || trade.name || shortMintValue(tradeMint(trade));
}

export function tradeReason(trade: TradeRecord): string {
  return trade.exit_reason || trade.close_reason || trade.failure_reason || trade.entry_reason || trade.reason || trade.status || "recorded";
}

export function tradePnlPct(trade: TradeRecord): number | null {
  const value = trade.total_pnl_pct ?? trade.pnl_pct;
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

export function tradePnl(trade: TradeRecord): number {
  const value = trade.total_pnl ?? trade.pnl ?? trade.realized_pnl ?? trade.unrealized_pnl;
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

export function tradeSizeUsd(trade: TradeRecord): number | null {
  const value = trade.size_usd ?? trade.entry_value;
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

export function tradeMarketCapIn(trade: TradeRecord): number | null {
  return normalizedNumber(trade.entry_market_cap ?? trade.market_cap_at_entry);
}

export function tradeMarketCapOut(trade: TradeRecord): number | null {
  return normalizedNumber(trade.exit_market_cap ?? trade.market_cap_at_exit ?? trade.current_market_cap ?? trade.market_cap);
}

export type TradesSummary = {
  openCount: number;
  closedCount: number;
  failedCount: number;
  openPnl: number;
  closedPnl: number;
  totalPnl: number;
};

export function summarizeTrades(trades: TradesPayload | null): TradesSummary {
  const openTrades = trades?.open_trades || [];
  const closedTrades = trades?.closed_trades || [];
  const openPnl = sumTradePnl(openTrades);
  const closedPnl = sumTradePnl(closedTrades);
  return {
    openCount: openTrades.length,
    closedCount: closedTrades.length,
    failedCount: trades?.failed_trades?.length || 0,
    openPnl,
    closedPnl,
    totalPnl: openPnl + closedPnl,
  };
}

export function tradeLedgerSourceLabel(trades: TradesPayload | null): string {
  if (!trades) return "loading source";
  const source = trades.source || "unknown";
  return trades.source_detail ? `${source} | ${trades.source_detail}` : source;
}

function sumTradePnl(trades: TradeRecord[]): number {
  return trades.reduce((total, trade) => total + tradePnl(trade), 0);
}

function normalizedNumber(value: unknown): number | null {
  return Number.isFinite(Number(value)) ? Number(value) : null;
}

function shortMintValue(mint: string): string {
  return mint.length > 14 ? `${mint.slice(0, 8)}...${mint.slice(-4)}` : mint || "-";
}
