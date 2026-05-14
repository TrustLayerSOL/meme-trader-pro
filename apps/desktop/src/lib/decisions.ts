import { shortMint } from "./format";

export type DecisionFilter =
  | "all"
  | "bought"
  | "skipped"
  | "co_main"
  | "market_radar"
  | "exploration"
  | "quote_failed"
  | "hard_risk"
  | "social"
  | "wallet";

export type DecisionRecord = {
  decision_id?: string;
  created_at?: number | string | null;
  updated_at?: number | string | null;
  mint?: string;
  signal_type?: string | null;
  final_action?: string | null;
  action_reason?: string | null;
  paper_lane?: string | null;
  total_score?: number | string | null;
  threshold?: number | string | null;
  risk_label?: string | null;
  buy_quote_pass?: boolean | null;
  sell_quote_pass?: boolean | null;
  wallet_count?: number | string | null;
  trade_status?: string | null;
  pnl?: number | string | null;
  pnl_pct?: number | string | null;
  paper_result?: Record<string, unknown> | null;
  result?: {
    trade_status?: string | null;
    pnl?: number | string | null;
    pnl_pct?: number | string | null;
    exit_reason?: string | null;
    failure_reason?: string | null;
    paper_outcome?: {
      paper_lane?: string | null;
      entry_price?: number | string | null;
      exit_price?: number | string | null;
      position_size_usd?: number | string | null;
      fees_usd?: number | string | null;
    } & Record<string, unknown>;
  } & Record<string, unknown>;
  payload?: {
    inputs?: {
      wallets?: string[];
      wallet_count?: number | string | null;
      social_match?: {
        matched?: boolean;
        reason?: string | null;
      };
      social_catalyst?: {
        matched?: boolean;
        account?: string | null;
        keywords?: string[];
        event_ids?: string[];
        catalyst_card_ids?: string[];
        match_confidence?: number | string | null;
      } & Record<string, unknown>;
      market_context?: {
        risk_regime?: string | null;
        sol_price_change_pct?: number | string | null;
        stablecoin_depeg_warning?: boolean | null;
        stablecoin?: Record<string, unknown> | null;
      } & Record<string, unknown>;
      market_info?: Record<string, unknown> | null;
      token_inspection?: {
        risk_label?: string | null;
        reasons?: string[];
      } | null;
    };
    rule_outcomes?: {
      risk?: {
        hard_block?: boolean;
        hard_block_reason?: string | null;
        warnings?: string[];
        holder_concentration?: {
          risk_label?: string | null;
          metrics?: Record<string, unknown> | null;
        } | null;
      };
      holder_cluster?: {
        holder_risk_label?: string | null;
        holder_count?: number | string | null;
        top_10_pct?: number | string | null;
        linked_wallet_risk?: { risk_label?: string | null } & Record<string, unknown>;
      } & Record<string, unknown>;
      scoring?: {
        reasons?: string[];
      };
    };
    quotes?: {
      buy?: { reason?: string | null; route?: string | null; price_impact_pct?: number | string | null };
      sell?: { reason?: string | null; route?: string | null; price_impact_pct?: number | string | null };
    };
    route_feasibility?: {
      buy?: RouteFeasibility;
      sell?: RouteFeasibility;
    };
    market_radar?: {
      decision?: {
        action?: string | null;
        open_reason?: string | null;
        skip_reason?: string | null;
        skip_bucket?: string | null;
        quote_retryable?: boolean | null;
      } & Record<string, unknown>;
    } & Record<string, unknown>;
    social_matched?: boolean;
  } & Record<string, unknown>;
} & Record<string, unknown>;

type RouteFeasibility = {
  pass?: boolean | null;
  reason?: string | null;
  route_count?: number | string | null;
  price_impact_pct?: number | string | null;
  slippage_bps?: number | string | null;
} & Record<string, unknown>;

export type DecisionLedgerPayload = {
  generated_at?: number;
  source?: string;
  live_execution_locked?: boolean;
  count?: number;
  filter?: string;
  lane?: string | null;
  items: DecisionRecord[];
};

export function decisionMatchesFilter(decision: DecisionRecord, filter: DecisionFilter): boolean {
  if (!filter || filter === "all") return true;
  const action = String(decision.final_action || "").toLowerCase();
  const payload = decision.payload || {};
  const inputs = payload.inputs || {};
  const risk = payload.rule_outcomes?.risk || {};

  if (filter === "bought") return action.includes("opened") || action.includes("open_attempt");
  if (filter === "skipped") return action.includes("skip") || action.includes("blocked") || action === "runtime_skip";
  if (filter === "co_main") return decision.paper_lane === "main" || decision.paper_lane === "market_radar";
  if (filter === "market_radar") return decision.paper_lane === "market_radar" || Boolean(payload.market_radar);
  if (filter === "exploration") return decision.paper_lane === "exploration";
  if (filter === "quote_failed") return decision.buy_quote_pass === false || decision.sell_quote_pass === false;
  if (filter === "hard_risk") return Boolean(risk.hard_block || decision.risk_label === "DANGER" || decision.risk_label === "EMERGENCY");
  if (filter === "social") return Boolean(inputs.social_match?.matched || payload.social_matched);
  if (filter === "wallet") return Boolean((inputs.wallets || []).length) || Number(inputs.wallet_count || decision.wallet_count || 0) > 0;
  return true;
}

export function filteredDecisions(rows: DecisionRecord[], filter: DecisionFilter): DecisionRecord[] {
  return rows.filter((decision) => decisionMatchesFilter(decision, filter));
}

export function selectedDecisionForFilter(rows: DecisionRecord[], selectedDecisionId: string, filter: DecisionFilter): DecisionRecord | null {
  const visible = filteredDecisions(rows, filter);
  return visible.find((decision) => decision.decision_id === selectedDecisionId) || visible[0] || null;
}

export function decisionQuotePair(decision: DecisionRecord): string {
  const buy = decision.buy_quote_pass === true ? "B+" : decision.buy_quote_pass === false ? "B-" : "B?";
  const sell = decision.sell_quote_pass === true ? "S+" : decision.sell_quote_pass === false ? "S-" : "S?";
  return `${buy}/${sell}`;
}

export function decisionWalletSummary(decision: DecisionRecord): string {
  const wallets = (decision.payload?.inputs?.wallets || []).filter(Boolean);
  return wallets.length ? wallets.map((wallet) => shortMint(wallet)).join(", ") : "-";
}

export function decisionSocialSummary(decision: DecisionRecord): string {
  const social = decision.payload?.inputs?.social_match;
  if (social?.reason) return social.reason;
  if (social?.matched || decision.payload?.social_matched) return "matched";
  return "-";
}

export function decisionRiskNotes(decision: DecisionRecord): string {
  const risk = decision.payload?.rule_outcomes?.risk;
  return (risk?.warnings || []).slice(0, 4).join("; ") || risk?.hard_block_reason || "-";
}

export function decisionScoreNotes(decision: DecisionRecord): string {
  return (decision.payload?.rule_outcomes?.scoring?.reasons || []).slice(0, 4).join("; ") || "-";
}

export function decisionQuoteReason(decision: DecisionRecord, side: "buy" | "sell"): string {
  const quote = decision.payload?.quotes?.[side];
  return quote?.reason || String(side === "buy" ? decision.buy_quote_pass ?? "-" : decision.sell_quote_pass ?? "-");
}

function present(value: unknown): value is string | number | boolean {
  return value !== null && value !== undefined && value !== "";
}

function compactParts(parts: Array<string | null | undefined | false>): string {
  return parts.filter(Boolean).join(" | ") || "-";
}

function formatCount(value: unknown, singular: string, plural: string): string | null {
  if (!Array.isArray(value)) return null;
  return `${value.length} ${value.length === 1 ? singular : plural}`;
}

function routeSideSummary(label: "Buy" | "Sell", route?: RouteFeasibility): string {
  if (!route) return `${label} unknown`;
  const state = route.pass === true ? "pass" : route.pass === false ? "blocked" : "unknown";
  const base = `${label} ${state}: ${route.reason || "-"}`;
  const detail = [
    present(route.route_count) ? `routes ${route.route_count}` : null,
    present(route.price_impact_pct) ? `impact ${route.price_impact_pct}%` : null,
    present(route.slippage_bps) ? `slip ${route.slippage_bps}bps` : null,
  ].filter(Boolean);
  return detail.length ? `${base}, ${detail.join(", ")}` : base;
}

export function decisionRouteFeasibilitySummary(decision: DecisionRecord): string {
  const route = decision.payload?.route_feasibility;
  if (!route) return "-";
  return `${routeSideSummary("Buy", route.buy)} | ${routeSideSummary("Sell", route.sell)}`;
}

export function decisionHolderClusterSummary(decision: DecisionRecord): string {
  const holder = decision.payload?.rule_outcomes?.holder_cluster;
  if (!holder) return "-";
  const linkedRisk = holder.linked_wallet_risk?.risk_label;
  return compactParts([
    holder.holder_risk_label || null,
    present(holder.holder_count) ? `holders ${holder.holder_count}` : null,
    present(holder.top_10_pct) ? `top 10 ${holder.top_10_pct}%` : null,
    linkedRisk ? `linked ${linkedRisk}` : null,
  ]);
}

export function decisionCatalystEvidenceSummary(decision: DecisionRecord): string {
  const catalyst = decision.payload?.inputs?.social_catalyst;
  if (!catalyst) return decisionSocialSummary(decision);
  return compactParts([
    catalyst.matched ? "matched" : null,
    catalyst.account ? `@${catalyst.account}` : null,
    catalyst.keywords?.length ? `keywords ${catalyst.keywords.slice(0, 4).join(", ")}` : null,
    formatCount(catalyst.event_ids, "event", "events"),
    formatCount(catalyst.catalyst_card_ids, "card", "cards"),
    present(catalyst.match_confidence) ? `confidence ${catalyst.match_confidence}` : null,
  ]);
}

export function decisionMarketContextSummary(decision: DecisionRecord): string {
  const context = decision.payload?.inputs?.market_context;
  if (!context) return "-";
  const stablecoinWarning =
    context.stablecoin_depeg_warning ?? context.stablecoin?.usdc_depeg_warning ?? context.stablecoin?.usdt_depeg_warning;
  return compactParts([
    context.risk_regime || null,
    present(context.sol_price_change_pct) ? `SOL ${context.sol_price_change_pct}%` : null,
    stablecoinWarning === true ? "stablecoin warning" : stablecoinWarning === false ? "stablecoin ok" : null,
  ]);
}

export function decisionMarketRadarSummary(decision: DecisionRecord): string {
  const radar = decision.payload?.market_radar?.decision;
  if (!radar) return "-";
  return compactParts([
    radar.open_reason ? `open ${radar.open_reason}` : null,
    radar.skip_reason ? `skip ${radar.skip_reason}` : null,
    radar.skip_bucket || null,
    radar.quote_retryable ? "retry soon" : null,
  ]);
}

export function decisionPaperOutcomeSummary(decision: DecisionRecord): string {
  const result = decision.result || {};
  const outcome = (result.paper_outcome || {}) as Record<string, unknown>;
  return compactParts([
    typeof result.trade_status === "string" ? result.trade_status : null,
    typeof outcome.paper_lane === "string" ? outcome.paper_lane : null,
    present(result.pnl_pct) ? `PnL ${result.pnl_pct}%` : null,
    present(outcome.entry_price) ? `entry ${outcome.entry_price}` : null,
    present(outcome.exit_price) ? `exit ${outcome.exit_price}` : null,
    present(outcome.position_size_usd) ? `size $${outcome.position_size_usd}` : null,
    present(outcome.fees_usd) ? `fees $${outcome.fees_usd}` : null,
    typeof result.exit_reason === "string" ? result.exit_reason : null,
  ]);
}

function asNumber(value: unknown): number | null {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function compactMoney(value: unknown): string | null {
  const numberValue = asNumber(value);
  if (numberValue === null) return null;
  const abs = Math.abs(numberValue);
  if (abs >= 1_000_000) return `$${(numberValue / 1_000_000).toFixed(abs >= 10_000_000 ? 1 : 2).replace(/\.0+$/, "")}M`;
  if (abs >= 1_000) return `$${(numberValue / 1_000).toFixed(abs >= 100_000 ? 0 : 1).replace(/\.0+$/, "")}K`;
  return `$${numberValue.toFixed(abs >= 100 ? 0 : 2)}`;
}

function percent(value: unknown): string | null {
  const numberValue = asNumber(value);
  return numberValue === null ? null : `${Number(numberValue.toFixed(2))}%`;
}

function firstKnown(source: Record<string, unknown> | null | undefined, keys: string[]): unknown {
  if (!source) return null;
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

export function decisionQuoteDetail(decision: DecisionRecord, side: "buy" | "sell"): string {
  const quote = decision.payload?.quotes?.[side];
  const pass = side === "buy" ? decision.buy_quote_pass : decision.sell_quote_pass;
  const impact = percent(quote?.price_impact_pct);
  const parts = [quote?.reason || String(pass ?? "-"), quote?.route ? `route ${quote.route}` : "", impact ? `impact ${impact}` : ""].filter(Boolean);
  return parts.join(" | ") || "-";
}

export function decisionRiskDetail(decision: DecisionRecord): string {
  const risk = decision.payload?.rule_outcomes?.risk;
  const tokenInspection = decision.payload?.inputs?.token_inspection;
  const holder = risk?.holder_concentration;
  const holderMetrics = holder?.metrics || {};
  const holderCount = firstKnown(holderMetrics as Record<string, unknown>, ["holder_count"]);
  const topOnePct = percent(firstKnown(holderMetrics as Record<string, unknown>, ["top_1_pct"]));
  const parts = [
    tokenInspection?.risk_label ? `Token mechanics ${tokenInspection.risk_label}` : "",
    (tokenInspection?.reasons || []).slice(0, 2).join("; "),
    holder?.risk_label ? `Holder concentration ${holder.risk_label}` : "",
    holderCount !== null ? `${holderCount} holders` : "",
    topOnePct ? `top 1 ${topOnePct}` : "",
    risk?.hard_block_reason ? `Hard block: ${risk.hard_block_reason}` : "",
    (risk?.warnings || []).slice(0, 3).join("; "),
  ].filter(Boolean);
  return parts.join(" | ") || decisionRiskNotes(decision);
}

export function decisionMarketSummary(decision: DecisionRecord): string {
  const market = (decision.payload?.inputs?.market_info || {}) as Record<string, unknown>;
  const marketCap = compactMoney(firstKnown(market, ["market_cap", "market_cap_usd", "mc"]));
  const liquidity = compactMoney(firstKnown(market, ["liquidity", "liquidity_usd", "liq"]));
  const holders = firstKnown(market, ["holders", "holder_count"]);
  const txCount = firstKnown(market, ["tx_count", "transactions", "txs"]);
  const parts = [
    marketCap ? `MC ${marketCap}` : "",
    liquidity ? `Liq ${liquidity}` : "",
    holders !== null ? `Holders ${holders}` : "",
    txCount !== null ? `Tx ${txCount}` : "",
  ].filter(Boolean);
  return parts.join(" | ") || "-";
}

export function decisionOutcomeSummary(decision: DecisionRecord): string {
  const raw = decision.result || decision.paper_result || {};
  const r = raw as Record<string, unknown>;
  const status = decision.trade_status || String(r.trade_status || "-");
  const pnlValue = compactMoney(decision.pnl ?? r.pnl);
  const pnlPct = percent(decision.pnl_pct ?? r.pnl_pct);
  const exitReason = (r.exit_reason || r.failure_reason || decision.action_reason) as string | undefined;
  const parts = [status, pnlValue || pnlPct ? `PnL ${pnlValue || "-"} / ${pnlPct || "-"}` : "", exitReason ? `exit ${exitReason}` : ""].filter(Boolean);
  return parts.join(" | ") || "-";
}
