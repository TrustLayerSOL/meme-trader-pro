const DEFAULT_API_BASE = "http://127.0.0.1:8765";
export const SELECTED_TOKEN_REFRESH_MS = 1000;
export const OVERVIEW_REFRESH_MS = 7000;
let desktopApiToken: string | null = initialDesktopApiToken();

export type { DecisionLedgerPayload } from "./decisions";

export type DecisionExplanationPayload = {
  generated_at?: number;
  source?: string;
  read_only?: boolean;
  advisory_only?: boolean;
  live_execution_locked?: boolean;
  execution_routes_enabled?: boolean;
  decision_id?: string;
  mint?: string;
  available?: boolean;
  status?: string;
  model?: string;
  response_id?: string | null;
  advisory?: string | null;
  detail?: string;
};

function initialDesktopApiToken(): string | null {
  try {
    const token = new URLSearchParams(window.location.search).get("api_token");
    return token || null;
  } catch {
    return null;
  }
}

export type ApiLaunchStatus = {
  running: boolean;
  started: boolean;
  detail: string;
  api_token?: string | null;
};

export type ChartMetric = "price" | "liquidity";
export type CandleInterval = 1 | 5 | 30 | 60;

export type Candle = {
  time: number;
  open?: number;
  high?: number;
  low?: number;
  close: number;
  volume?: number;
  color?: string;
};

export type CandlesPayload = {
  metric: ChartMetric;
  interval_seconds?: number;
  snapshot_count: number;
  candles: Candle[];
};

export type ProtectionSummary = {
  state?: string;
  risk_level?: string;
  alert_level?: string;
  reason?: string;
  quote_status?: string;
  quote_reason?: string;
  suggested_sell_pct?: number;
  urgency?: string;
  token_amount?: number | null;
  token_amount_raw?: number | null;
  token_amount_source?: string | null;
  token_amount_updated_at?: string | null;
  token_amount_reason?: string | null;
  token_decimals?: number | null;
  test_amount?: boolean;
  amount_safety_note?: string | null;
  wallet_balance_status?: string | null;
  wallet_balance_accounts?: number | null;
  wallet_balance_reason?: string | null;
  token_standard?: string;
  token_extensions?: string[];
  token_mechanics_risk?: string;
  price_from_peak_pct?: number;
  liquidity_from_peak_pct?: number;
  live_action_allowed?: boolean;
  auto_sell_enabled?: boolean;
  reasons?: string[];
};

export type WatchlistItem = {
  token_mint?: string;
  mint?: string;
  name?: string;
  symbol?: string;
  status?: string;
  risk_level?: string;
  alert_level?: string;
  reason?: string;
  quote_status?: string;
  quote_reason?: string;
  suggested_sell_pct?: number;
  urgency?: string;
  token_amount?: number | null;
  token_amount_raw?: number | null;
  token_amount_source?: string | null;
  token_amount_updated_at?: string | null;
  token_amount_reason?: string | null;
  token_decimals?: number | null;
  test_amount?: boolean;
  amount_safety_note?: string | null;
  wallet_balance_status?: string | null;
  wallet_balance_accounts?: number | null;
  wallet_balance_reason?: string | null;
  auto_sell?: boolean;
  alert_only?: boolean;
  external_position?: boolean;
  live_action_allowed?: boolean;
  current_price?: number | null;
  current_liquidity?: number | null;
  baseline_price?: number | null;
  baseline_liquidity?: number | null;
  peak_price?: number | null;
  peak_liquidity?: number | null;
  price_from_entry_pct?: number | null;
  price_from_peak_pct?: number | null;
  liquidity_from_entry_pct?: number | null;
  liquidity_from_peak_pct?: number | null;
  holder_count?: number | null;
  holder_top_10_pct?: number | null;
  token_standard?: string;
  token_extensions?: string[];
  token_mechanics_risk?: string;
  token_mechanics_reasons?: string[];
  wallet?: string;
  created_at?: string;
  last_update?: string;
  market_source?: string;
  url?: string;
};

export type WatchlistPayload = {
  generated_at?: number;
  source?: string;
  count?: number;
  items: WatchlistItem[];
};

export type ProtectedAmountRequest = {
  mint: string;
  wallet?: string;
  amount?: string;
  decimals?: string;
  raw?: string;
  test?: boolean;
};

export type ProtectedTokenRequest = ProtectedAmountRequest & {
  alert_only?: boolean;
  external_position?: boolean;
  exit_priority?: string;
  requested_auto_sell?: boolean;
};

export type ProtectedAmountResponse = {
  generated_at?: number;
  mode: "PROTECTED_METADATA_ONLY" | "PROTECTED_WATCH_ONLY";
  live_execution_locked: boolean;
  auto_sell_enabled: boolean;
  execution_routes_enabled: boolean;
  action?: string;
  item: WatchlistItem;
  detail?: string;
};

export type WalletRow = {
  wallet: string;
  name?: string;
  emoji?: string;
  groups?: string[];
  signals?: number;
  paper_entries?: number;
  wins?: number;
  losses?: number;
  win_rate_pct?: number | null;
  total_pnl?: number;
  avg_pnl?: number;
  best_pnl?: number;
  worst_pnl?: number;
  score?: number;
  label?: string;
  last_seen?: number | null;
  last_seen_age_seconds?: number | null;
};

export type WalletSignal = {
  time?: number;
  mint?: string;
  wallets?: string[];
  signal_type?: string;
  score?: number;
  should_trade?: boolean;
  token_age_seconds?: number | null;
};

export type WalletsPayload = {
  generated_at?: number;
  source?: string;
  live_execution_locked: boolean;
  tracked_count: number;
  performance_count: number;
  wallets: WalletRow[];
  recent_signals: WalletSignal[];
};

export type WalletTradeSummary = {
  source?: string;
  mint?: string;
  symbol?: string;
  status?: string;
  pnl_pct?: number | null;
  pnl?: number | null;
  reason?: string | null;
  wallets?: string[];
};

export type WalletPostmortemTrade = {
  mint?: string;
  symbol?: string;
  status?: string;
  source?: string;
  pnl_pct?: number | null;
  pnl?: number | null;
  reason?: string;
  hold_seconds?: number;
  time?: number;
};

export type WalletPostmortemRollup = {
  closed_trades?: number;
  failed_trades?: number;
  best_trade?: WalletPostmortemTrade | null;
  worst_trade?: WalletPostmortemTrade | null;
  exit_reasons?: Record<string, number>;
  failure_reasons?: Record<string, number>;
  avg_hold_seconds?: number;
  recent_outcomes?: WalletPostmortemTrade[];
};

export type WalletDetailPayload = {
  generated_at?: number;
  read_only: boolean;
  live_execution_locked: boolean;
  wallet: WalletRow;
  recent_signals: WalletSignal[];
  paper_trades: WalletTradeSummary[];
  behavior?: {
    labels?: string[];
    rolling?: Record<string, WalletRollingWindow>;
  };
  postmortem?: WalletPostmortemRollup;
};

export type CandidateWallet = {
  wallet: string;
  already_tracked: boolean;
  score?: number;
  recommended_tier?: string;
  buy_events?: number;
  sell_events?: number;
  early_buy_events?: number;
  unique_mints?: number;
  winner_mints?: number;
  sell_ratio?: number;
  first_seen?: number | null;
  last_seen?: number | null;
  reasons?: string[];
  review?: {
    action?: string;
    mode?: string;
    mutates_tracked_wallets?: boolean;
    reasons?: string[];
    blockers?: string[];
  };
  evidence?: Array<{ mint?: string; side?: string; delta?: number; time?: number; signature?: string }>;
};

export type CandidateWalletsPayload = {
  generated_at?: number;
  source?: string;
  mode: "WATCH_ONLY_REVIEW" | string;
  read_only: boolean;
  live_execution_locked: boolean;
  summary?: {
    candidate_wallets?: number;
    untracked_wallets?: number;
    tracked_wallets?: number;
  };
  source_counts?: Record<string, number>;
  review_summary?: Record<string, number>;
  count: number;
  candidates: CandidateWallet[];
};

export type WalletLifecycleMetrics = {
  entries: number;
  wins: number;
  losses: number;
  score: number;
  avg_pnl: number;
  total_pnl: number;
  win_rate: number;
};

export type WalletRollingWindow = {
  entries?: number;
  wins?: number;
  losses?: number;
  win_rate?: number;
  avg_pnl?: number;
  total_pnl?: number;
  median_hold_seconds?: number;
};

export type WalletLifecycleDecision = {
  wallet: string;
  action: string;
  target_tier: string;
  current_source: string;
  mutates_live_tracking: boolean;
  live_trade_driver: boolean;
  metrics: WalletLifecycleMetrics;
  labels?: string[];
  rolling?: Record<string, WalletRollingWindow>;
  postmortem?: WalletPostmortemRollup;
  reasons: string[];
  blockers: string[];
};

export type WalletLifecycleRow = {
  wallet: string;
  source: string;
  lifecycle: WalletLifecycleDecision;
};

export type WalletLifecyclePayload = {
  generated_at?: number;
  mode: "REVIEW_ONLY" | string;
  read_only: boolean;
  live_execution_locked: boolean;
  summary?: {
    wallets?: number;
    promotion_review?: number;
    demote_review?: number;
  };
  count: number;
  wallets: WalletLifecycleRow[];
};

export type WalletReviewDecisionRequest = {
  wallet: string;
  decision: "approve_promotion" | "approve_demotion" | "hold" | "reject";
  approved?: boolean;
  note?: string;
};

export type WalletReviewDecisionResponse = {
  generated_at?: number;
  mode: "WALLET_REVIEW_DECISION_ONLY";
  live_execution_locked: boolean;
  tracked_wallets_mutated: boolean;
  decision: {
    wallet: string;
    decision: string;
    approved: boolean;
    note?: string;
    approved_by?: string;
    approved_at?: number | string;
    updated_at?: number;
  };
  summary: Record<string, number>;
};

export type WalletReviewApplyPayload = {
  generated_at?: number;
  mode: "WALLET_REVIEW_APPLY";
  live_execution_locked: boolean;
  execution_routes_enabled: boolean;
  dry_run: boolean;
  stamp?: string;
  backup_dir?: string | null;
  summary: {
    approved_decisions?: number;
    promoted?: number;
    demoted?: number;
    skipped?: number;
    tracked_wallets_after?: number;
    bad_wallets_after?: number;
  };
  changes: Array<{
    wallet?: string;
    action?: string;
    lifecycle_action?: string;
    metrics?: WalletLifecycleMetrics;
  }>;
  skipped: Array<{ wallet?: string; reason?: string }>;
  detail?: string;
};

export type OperatorConfigPayload = {
  generated_at?: number;
  read_only: boolean;
  live_execution_locked: boolean;
  selected_token_refresh_ms: number;
  overview_refresh_ms: number;
  strategy: Record<string, string | number | boolean | null | undefined>;
  mode_blocks: Record<string, Record<string, string | number | boolean | null | undefined>>;
  runtime?: {
    state?: string;
    components?: Array<{ name: string; state: string; fresh: boolean; age_seconds?: number | null; detail?: string }>;
  };
  providers?: {
    state: string;
    active_provider?: string | null;
    live_execution_unlocked?: boolean;
    providers: Array<{
      name: string;
      ok: boolean;
      http_status?: number;
      error?: string;
      detail?: string;
      safe_url?: string;
    }>;
  };
  safety: {
    paper_first: boolean;
    auto_sell_enabled: boolean;
    mutations_enabled: boolean;
    execution_routes_enabled: boolean;
  };
};

export type LogsPayload = {
  generated_at?: number;
  read_only: boolean;
  live_execution_locked: boolean;
  logs: Record<string, { path: string; exists: boolean; lines: string[] }>;
};

export type SignalSummary = {
  social_count: number;
  catalyst_count: number;
  social: Array<{ account?: string; text?: string; keywords?: string[] }>;
  catalysts: Array<{ mint?: string; symbol?: string; summary?: string; sources?: string[]; snapshot_count?: number }>;
};

export type CandidateFeedItem = {
  time?: number;
  age_seconds?: number | null;
  mint: string;
  source?: string;
  context?: string;
  status: "TRADE_READY" | "SKIPPED" | "BLOCKED" | string;
  name?: string | null;
  symbol?: string | null;
  image_url?: string | null;
  price?: number | null;
  market_cap?: number | null;
  market_cap_estimated?: boolean;
  liquidity?: number | null;
  volume?: number | null;
  tx_count?: number | null;
  holder_count?: number | null;
  wallet_count?: number | null;
  weighted_wallet_score?: number | null;
  total_score?: number | null;
  edge_score?: number | null;
  risk_label?: string | null;
  token_mechanics_risk?: string | null;
  should_trade?: boolean | null;
  reasons?: string[];
  url?: string | null;
};

export type CandidateFeedPayload = {
  generated_at?: number;
  source?: string;
  live_execution_locked: boolean;
  count: number;
  items: CandidateFeedItem[];
};

export type EventFeedItem = {
  time?: number;
  age_seconds?: number | null;
  type: string;
  wallet?: string | null;
  mint?: string | null;
  name?: string | null;
  symbol?: string | null;
  image_url?: string | null;
  amount?: number | null;
  price?: number | null;
  market_cap?: number | null;
  liquidity?: number | null;
  tx_count?: number | null;
  holder_count?: number | null;
  wallet_quality_score?: number | null;
  wallet_performance_score?: number | null;
  combined_wallet_score?: number | null;
  source?: string | null;
};

export type EventFeedPayload = {
  generated_at?: number;
  source?: string;
  live_execution_locked: boolean;
  count: number;
  items: EventFeedItem[];
};

export type PositionDetailPayload = {
  mint: string;
  snapshot_count: number;
  position_source?: string | null;
  position_source_detail?: string | null;
  snapshot_source?: string | null;
  snapshot_source_detail?: string | null;
  source_contract?: {
    position?: string;
    snapshots?: string;
    social?: string;
    catalysts?: string;
    wallet_stats?: string;
    wallet_context?: string;
  };
  mixed_market_fields?: boolean;
  mixed_market_fields_note?: string;
  position?: {
    source?: string;
    label?: string;
    status?: string;
    price?: number;
    market_cap?: number;
    liquidity?: number;
    risk_level?: string | null;
    alert_level?: string | null;
    pnl_pct?: number | null;
    quote_status?: string | null;
    holder_count?: number | null;
    top_10_holder_pct?: number | null;
    live_action_allowed?: boolean;
  };
  latest_snapshot?: {
    market_info?: {
      name?: string | null;
      symbol?: string | null;
      price?: number | null;
      liquidity?: number | null;
      market_cap?: number | null;
      volume?: number | null;
      price_change_24h?: number | null;
      dex?: string | null;
      url?: string | null;
    };
    buy_quote_pass?: boolean;
    buy_quote_reason?: string | null;
    buy_quote_price_impact_pct?: number | null;
    sell_quote_pass?: boolean;
    sell_quote_reason?: string | null;
    sell_quote_price_impact_pct?: number | null;
    wallet_count?: number;
    weighted_wallet_score?: number;
    total_score?: number;
    score_threshold?: number;
    mode?: string;
    should_trade?: boolean;
    risk_label?: string;
    risk_score?: number;
    risk_warnings?: string[];
    hard_block?: boolean;
    hard_block_reason?: string | null;
    token_standard?: string;
    token_extensions?: string[];
    token_mechanics_risk?: string;
    token_mechanics_reasons?: string[];
    holder_concentration_risk?: string;
    holder_count?: number | null;
    holder_top_1_pct?: number | null;
    holder_top_5_pct?: number | null;
    holder_top_10_pct?: number | null;
    dev_wallet?: string | null;
    dev_label?: string;
    dev_bonded_tokens?: number;
    score_reasons?: string[];
    confirmation_allow?: boolean;
    confirmation_reasons?: string[];
    confirmation_warnings?: string[];
    strategy_guard_action?: string;
    strategy_guard_reason?: string;
  };
  trend?: {
    price_change_pct?: number;
    liquidity_change_pct?: number;
    latest_source?: string;
    latest_context?: string;
    latest_age_seconds?: number;
  };
  protection?: ProtectionSummary;
  signals?: SignalSummary;
  wallet_context?: TokenWalletContext;
};

export type TokenWalletContext = {
  wallet_count: number;
  matched_signals: number;
  proven_wallets: number;
  trap_wallets: number;
  avg_score: number;
  live_execution_locked: boolean;
  wallets: Array<WalletRow & {
    labels?: string[];
    rolling?: Record<string, WalletRollingWindow>;
    postmortem?: WalletPostmortemRollup;
    matched_signal_count?: number;
  }>;
};

export type ReadinessPayload = {
  overall: string;
  counts?: Record<string, number>;
  rows?: Array<{ check: string; status: string; detail: string }>;
  sqlite_counts?: Record<string, number>;
};

export type FreshnessPayload = {
  generated_at?: number;
  freshness: {
    overall: string;
    counts?: Record<string, number>;
    rows?: Array<{
      source: string;
      status: string;
      age: string;
      size: string;
      path: string;
      owner?: string;
      detail?: string;
    }>;
  };
  social?: SocialFreshnessPayload;
};

export type SocialFreshnessRow = {
  source: string;
  label?: string;
  status: string;
  age?: string;
  age_seconds?: number | null;
  fresh_seconds?: number | null;
  event_count?: number;
  enabled?: boolean;
  last_success_at?: number | string | null;
  last_error?: string | null;
  collector_type?: string;
  detail?: string;
};

export type SocialFreshnessPayload = {
  generated_at?: number;
  mode: "SOCIAL_FRESHNESS_READ_ONLY" | string;
  live_execution_locked: boolean;
  overall: string;
  counts?: Record<string, number>;
  rows: SocialFreshnessRow[];
  detail?: string;
};

export type DecisionAnalyticsSummary = {
  label?: string;
  candidate_decisions: number;
  paper_attempts: number;
  paper_opened: number;
  skipped: number;
  quote_failed: number;
  hard_blocked: number;
  social_confirmed: number;
  wallet_confirmed: number;
  open_trades: number;
  closed_trades: number;
  failed_trades: number;
  wins: number;
  losses: number;
  total_pnl: number;
  avg_pnl_pct?: number | null;
  win_rate: number;
  expectancy_pnl?: number;
  attempt_to_open_rate?: number;
  decision_to_close_rate?: number;
  sample_ready: boolean;
};

export type DecisionAnalyticsPayload = {
  generated_at?: number;
  source: string;
  live_execution_locked: boolean;
  total_decisions: number;
  overall: DecisionAnalyticsSummary;
  lanes: Record<string, DecisionAnalyticsSummary>;
  groups: Record<string, DecisionAnalyticsSummary>;
  social_expansion_gate: {
    allowed: boolean;
    reason?: string;
    minimum_labeled_social_outcomes?: number;
    current_labeled_social_outcomes?: number;
  };
  notes?: string[];
};

export type TradeRecord = {
  mint?: string;
  token_mint?: string;
  symbol?: string;
  name?: string;
  status?: string;
  paper_lane?: string;
  exploration?: boolean;
  entry_reason?: string;
  exit_reason?: string;
  close_reason?: string | null;
  failure_reason?: string;
  total_pnl_pct?: number;
  pnl_pct?: number;
  total_pnl?: number;
  pnl?: number;
  realized_pnl?: number;
  unrealized_pnl?: number;
  current_market_cap?: number;
  market_cap?: number;
  entry_market_cap?: number;
  market_cap_at_entry?: number;
  exit_market_cap?: number;
  market_cap_at_exit?: number;
  current_liquidity_usd?: number;
  entry_liquidity_usd?: number;
  liquidity_usd?: number;
  reason?: string;
  wallets?: string[];
  quoted_entry_price?: number;
  entry_price?: number;
  current_price?: number;
  exit_price?: number;
  close_price?: number;
  size_usd?: number;
  entry_value?: number;
  current_value?: number;
  remaining_pct?: number;
  entry_fee_usd?: number;
  total_fees_usd?: number;
  entry_time?: number;
  entry_time_iso?: string;
  close_time?: number | null;
  close_time_iso?: string;
  exit_time_iso?: string;
  sells?: unknown[];
  exit_advice?: {
    action?: string;
    severity?: string;
    reasons?: string[];
    pnl_pct?: number;
    price_from_high_pct?: number;
    liquidity_change_pct?: number;
    age_seconds?: number;
  };
};

export type TradesPayload = {
  source?: string;
  source_detail?: string;
  source_contract?: {
    trades?: string;
    decisions?: string;
    snapshots?: string;
  };
  open_trades: TradeRecord[];
  closed_trades: TradeRecord[];
  failed_trades: TradeRecord[];
};

export type WinnerPatternTrade = {
  mint?: string;
  symbol?: string;
  pnl?: number;
  pnl_pct?: number | null;
  entry_market_cap?: number | null;
  exit_market_cap?: number | null;
  entry_liquidity?: number | null;
  entry_reason?: string;
  exit_reason?: string;
  wallets?: string[];
};

export type WinnerPatternPayload = {
  generated_at?: number;
  mode: "WINNER_PATTERN_REVIEW_ONLY";
  live_execution_locked: boolean;
  winner_count: number;
  big_winner_count: number;
  loser_count: number;
  sample_warning?: string;
  repeatable_traits: string[];
  trait_counts: Record<string, number>;
  wallet_leaders: Array<{ wallet: string; wins: number; pnl: number; best_pnl: number }>;
  top_winners: WinnerPatternTrade[];
  worst_losers: WinnerPatternTrade[];
  recommended_actions: string[];
};

export type SnapshotPayload = {
  source?: string;
  source_detail?: string;
  source_contract?: {
    snapshots?: string;
    trades?: string;
    decisions?: string;
  };
  snapshots: Array<{
    time?: number;
    source?: string;
    context?: string;
    price?: number;
    liquidity?: number;
    risk_label?: string;
    token_standard?: string;
    token_mechanics_risk?: string;
    token_mechanics_reasons?: string[];
    holder_concentration_risk?: string;
    holder_count?: number | null;
    holder_top_1_pct?: number | null;
    holder_top_5_pct?: number | null;
    holder_top_10_pct?: number | null;
  }>;
};

export type TokenState = {
  detail: PositionDetailPayload;
  candles: CandlesPayload;
  snapshots: SnapshotPayload;
};

export type SocialImportRequest = {
  mint?: string;
  account?: string;
  text: string;
};

export type SocialImportResponse = {
  imported?: boolean;
  ok?: boolean;
  count?: number;
  detail?: string;
};

type TauriGlobal = {
  core?: {
    invoke: <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
  };
};

declare global {
  interface Window {
    __TAURI__?: TauriGlobal;
  }
}

export function desktopApiUrl(path: string): URL {
  if (!path.startsWith("/api/")) {
    throw new Error("MemeTraderPro desktop shell only allows local /api paths.");
  }
  return new URL(path, DEFAULT_API_BASE);
}

export function setDesktopApiToken(token?: string | null) {
  desktopApiToken = token || null;
}

export async function fetchJson<T>(path: string): Promise<T> {
  const url = desktopApiUrl(path);
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const url = desktopApiUrl(path);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (desktopApiToken) headers["X-MemeTraderPro-Token"] = desktopApiToken;
  const response = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const errorPayload = await response.json() as { error?: string };
      detail = errorPayload.error || detail;
    } catch {
      // Keep the HTTP status fallback.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export function tokenApiPaths(mint: string, metric: ChartMetric = "price", interval: CandleInterval = 1) {
  const encoded = encodeURIComponent(mint);
  return {
    detail: `/api/positions/${encoded}`,
    candles: `/api/candles?mint=${encoded}&limit=240&metric=${metric}&interval=${interval}`,
    snapshots: `/api/tokens/${encoded}/snapshots?limit=25`,
  };
}

export function walletDetailApiPath(wallet: string) {
  return `/api/wallets/${encodeURIComponent(wallet)}?limit=40`;
}

export function candidateWalletsApiPath(limit = 80) {
  return `/api/candidate-wallets?limit=${encodeURIComponent(String(limit))}`;
}

export function walletLifecycleApiPath(limit = 80) {
  return `/api/wallet-lifecycle?limit=${encodeURIComponent(String(limit))}`;
}

export function candidateFeedApiPath(limit = 80) {
  return `/api/candidates?limit=${encodeURIComponent(String(limit))}`;
}

export function eventFeedApiPath(limit = 120) {
  return `/api/events?limit=${encodeURIComponent(String(limit))}`;
}

export function decisionLedgerApiPath(options: { limit?: number; filter?: string; lane?: string } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 80));
  if (options.filter) params.set("filter", options.filter);
  if (options.lane) params.set("lane", options.lane);
  return `/api/decisions?${params.toString()}`;
}

export function decisionExplanationApiPath(decisionId: string) {
  return `/api/decisions/${encodeURIComponent(decisionId)}/explanation`;
}

export function protectedAmountApiPath() {
  return "/api/watchlist/protected-amount";
}

export function protectedTokenApiPath() {
  return "/api/watchlist/protected-token";
}

export function winnerPatternsApiPath() {
  return "/api/winner-patterns";
}

export function walletReviewDecisionApiPath() {
  return "/api/wallet-review-decision";
}

export function walletReviewApplyApiPath() {
  return "/api/wallet-review-apply";
}

export function socialImportApiPath() {
  return "/api/social/import";
}

export function socialFreshnessApiPath() {
  return "/api/social/freshness";
}

export function decisionAnalyticsApiPath(limit = 5000) {
  return `/api/decision-analytics?limit=${encodeURIComponent(String(limit))}`;
}

export function loadDecisionExplanation(decisionId: string) {
  return fetchJson<DecisionExplanationPayload>(decisionExplanationApiPath(decisionId));
}

export function saveProtectedAmount(payload: ProtectedAmountRequest) {
  return postJson<ProtectedAmountResponse>(protectedAmountApiPath(), payload);
}

export function saveProtectedToken(payload: ProtectedTokenRequest) {
  return postJson<ProtectedAmountResponse>(protectedTokenApiPath(), payload);
}

export function saveWalletReviewDecision(payload: WalletReviewDecisionRequest) {
  return postJson<WalletReviewDecisionResponse>(walletReviewDecisionApiPath(), payload);
}

export function applyWalletReviewChanges() {
  return postJson<WalletReviewApplyPayload>(walletReviewApplyApiPath(), { confirm: "APPLY_WALLET_REVIEW" });
}

export function importSocialPost(payload: SocialImportRequest) {
  return postJson<SocialImportResponse>(socialImportApiPath(), payload);
}

export async function loadTokenState(mint: string, metric: ChartMetric = "price", interval: CandleInterval = 1): Promise<TokenState> {
  const paths = tokenApiPaths(mint, metric, interval);
  const [detail, candles, snapshots] = await Promise.all([
    fetchJson<PositionDetailPayload>(paths.detail),
    fetchJson<CandlesPayload>(paths.candles),
    fetchJson<SnapshotPayload>(paths.snapshots),
  ]);
  return { detail, candles, snapshots };
}

export async function ensureDesktopApi(): Promise<ApiLaunchStatus> {
  const invoke = window.__TAURI__?.core?.invoke;
  if (!invoke) {
    return {
      running: false,
      started: false,
      detail: "Tauri launcher bridge unavailable; using existing local API if present.",
    };
  }
  return invoke<ApiLaunchStatus>("ensure_desktop_api");
}
