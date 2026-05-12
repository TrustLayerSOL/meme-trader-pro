import { useEffect, useState, type FormEvent } from "react";
import { LockedActions } from "./components/LockedActions";
import { DecisionLedger } from "./components/DecisionLedger";
import { OpsPanel } from "./components/OpsPanel";
import { EmptyState, LoadingState } from "./components/PanelState";
import { PositionMonitor } from "./components/PositionMonitor";
import { ProtectionDrilldown } from "./components/ProtectionDrilldown";
import { TokenDetail } from "./components/TokenDetail";
import { TradeLifecycle } from "./components/TradeLifecycle";
import { TradingChart } from "./components/TradingChart";
import { WalletIntelligence } from "./components/WalletIntelligence";
import {
  candidateFeedApiPath,
  candidateWalletsApiPath,
  decisionLedgerApiPath,
  ensureDesktopApi,
  eventFeedApiPath,
  fetchJson,
  importSocialPost,
  loadTokenState,
  OVERVIEW_REFRESH_MS,
  SELECTED_TOKEN_REFRESH_MS,
  setDesktopApiToken,
  walletDetailApiPath,
  walletReviewApplyApiPath,
  walletLifecycleApiPath,
  winnerPatternsApiPath,
  type ApiLaunchStatus,
  type CandlesPayload,
  type CandleInterval,
  type CandidateFeedPayload,
  type CandidateFeedItem,
  type CandidateWalletsPayload,
  type ChartMetric,
  type EventFeedPayload,
  type EventFeedItem,
  type WalletDetailPayload,
  type WalletReviewApplyPayload,
  type WalletLifecyclePayload,
  type FreshnessPayload,
  type LogsPayload,
  type OperatorConfigPayload,
  type PositionDetailPayload,
  type ReadinessPayload,
  type SnapshotPayload,
  type TradeRecord,
  type TradesPayload,
  type WatchlistItem,
  type WatchlistPayload,
  type WinnerPatternPayload,
  type WalletsPayload,
} from "./lib/api";
import type { DecisionLedgerPayload } from "./lib/decisions";
import { money, pct, price, shortMint } from "./lib/format";
import { findTradeForMint, summarizeTrades, tradeLabel, tradeMarketCapIn, tradeMarketCapOut, tradeMint, tradePnl, tradePnlPct, tradeReason, tradeSizeUsd } from "./lib/trades";

type RuntimeComponent = {
  name: string;
  state: string;
  fresh: boolean;
};

type Overview = {
  mode: string;
  live_execution_locked: boolean;
  runtime: {
    state: string;
    components: RuntimeComponent[];
  };
  counts: Record<string, number>;
  wallet_confidence?: OperatorWalletConfidence;
};

type OperatorWalletConfidence = {
  wallet_count: number;
  signal_count: number;
  token_count: number;
  proven_wallets: number;
  trap_wallets: number;
  open_trade_wallets: number;
  avg_score: number;
  top_labels: Record<string, number>;
  live_execution_locked: boolean;
  wallets: Array<{
    wallet: string;
    score?: number;
    paper_entries?: number;
    avg_pnl?: number;
    labels?: string[];
    postmortem?: {
      closed_trades?: number;
      failed_trades?: number;
    };
    open_trade_driver?: boolean;
  }>;
};

type Position = {
  mint: string;
  label: string;
  source: string;
  status: string;
  price: number | null;
  market_cap?: number | null;
  liquidity: number | null;
  risk_level: string | null;
  alert_level: string | null;
  quote_status?: string | null;
  holder_count?: number | null;
  top_10_holder_pct?: number | null;
  pnl_pct?: number | null;
};

type PositionsPayload = {
  positions: Position[];
};

type PaperReviewPayload = {
  mode: string;
  live_execution_locked: boolean;
  meaningful_test_ready: boolean;
  main_meaningful_test_ready?: boolean;
  exploration_sample_ready?: boolean;
  minimum_closed_trades: number;
  recommended_closed_trades: number;
  open_trades: number;
  metrics: {
    open_trades: number;
    closed_trades: number;
    failed_trades: number;
    realized_pnl: number;
    total_pnl: number;
    win_rate: number;
    expectancy: number;
    profit_factor?: number | null;
    max_drawdown: number;
    avg_win: number;
    avg_loss: number;
    signal_rows?: Array<{ signal: string; trades: number; win_rate: number; total_pnl: number; avg_pnl: number }>;
  };
  lane_metrics?: Record<string, {
    open_trades: number;
    closed_trades: number;
    failed_trades: number;
    realized_pnl: number;
    total_pnl: number;
    win_rate: number;
    expectancy: number;
    profit_factor?: number | null;
  }>;
  readiness_gaps: string[];
  exit_reasons: Record<string, number>;
  failure_reasons: Record<string, number>;
  entry_reasons: Record<string, number>;
  wallet_label_exposure: Record<string, number>;
  next_review_actions: string[];
};

type WorkArea = "cockpit" | "portfolio" | "details" | "protection" | "wallets" | "signals" | "replay" | "ops" | "system";

const CANDLE_INTERVALS: Array<{ value: CandleInterval; label: string }> = [
  { value: 1, label: "1s" },
  { value: 5, label: "5s" },
  { value: 30, label: "30s" },
  { value: 60, label: "1m" },
];

export function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [selectedMint, setSelectedMint] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [apiStatus, setApiStatus] = useState<ApiLaunchStatus | null>(null);
  const [chartMetric, setChartMetric] = useState<ChartMetric>("price");
  const [candleInterval, setCandleInterval] = useState<CandleInterval>(1);
  const [tokenDetail, setTokenDetail] = useState<PositionDetailPayload | null>(null);
  const [candles, setCandles] = useState<CandlesPayload | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotPayload | null>(null);
  const [readiness, setReadiness] = useState<ReadinessPayload | null>(null);
  const [freshness, setFreshness] = useState<FreshnessPayload | null>(null);
  const [trades, setTrades] = useState<TradesPayload | null>(null);
  const [decisions, setDecisions] = useState<DecisionLedgerPayload | null>(null);
  const [paperReview, setPaperReview] = useState<PaperReviewPayload | null>(null);
  const [winnerPatterns, setWinnerPatterns] = useState<WinnerPatternPayload | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistPayload | null>(null);
  const [wallets, setWallets] = useState<WalletsPayload | null>(null);
  const [candidateWallets, setCandidateWallets] = useState<CandidateWalletsPayload | null>(null);
  const [walletLifecycle, setWalletLifecycle] = useState<WalletLifecyclePayload | null>(null);
  const [walletApply, setWalletApply] = useState<WalletReviewApplyPayload | null>(null);
  const [selectedWallet, setSelectedWallet] = useState<string>("");
  const [walletDetail, setWalletDetail] = useState<WalletDetailPayload | null>(null);
  const [operatorConfig, setOperatorConfig] = useState<OperatorConfigPayload | null>(null);
  const [logs, setLogs] = useState<LogsPayload | null>(null);
  const [candidates, setCandidates] = useState<CandidateFeedPayload | null>(null);
  const [events, setEvents] = useState<EventFeedPayload | null>(null);
  const [tokenError, setTokenError] = useState<string>("");
  const [workArea, setWorkArea] = useState<WorkArea>("cockpit");

  useEffect(() => {
    let cancelled = false;
    let ensured = false;
    let inFlight = false;
    async function load() {
      if (inFlight) return;
      inFlight = true;
      try {
        if (!ensured) {
          const launchStatus = await ensureDesktopApi();
          ensured = true;
          if (cancelled) return;
          setDesktopApiToken(launchStatus.api_token || null);
          setApiStatus(launchStatus);
        }
        const [overviewPayload, positionsPayload] = await Promise.all([
          fetchJson<Overview>("/api/overview"),
          fetchJson<PositionsPayload>("/api/positions"),
        ]);
        const optional = await Promise.allSettled([
          fetchJson<ReadinessPayload>("/api/readiness"),
          fetchJson<FreshnessPayload>("/api/freshness"),
          fetchJson<TradesPayload>("/api/trades"),
          fetchJson<DecisionLedgerPayload>(decisionLedgerApiPath()),
          fetchJson<PaperReviewPayload>("/api/paper-review"),
          fetchJson<WinnerPatternPayload>(winnerPatternsApiPath()),
          fetchJson<WatchlistPayload>("/api/watchlist"),
          fetchJson<WalletsPayload>("/api/wallets"),
          fetchJson<CandidateWalletsPayload>(candidateWalletsApiPath()),
          fetchJson<WalletLifecyclePayload>(walletLifecycleApiPath()),
          fetchJson<WalletReviewApplyPayload>(walletReviewApplyApiPath()),
          fetchJson<OperatorConfigPayload>("/api/operator-config"),
          fetchJson<LogsPayload>("/api/logs?limit=40"),
          fetchJson<CandidateFeedPayload>(candidateFeedApiPath()),
          fetchJson<EventFeedPayload>(eventFeedApiPath()),
        ]);
        if (cancelled) return;
        const [readinessResult, freshnessResult, tradesResult, decisionsResult, paperReviewResult, winnerPatternsResult, watchlistResult, walletsResult, candidateWalletsResult, walletLifecycleResult, walletApplyResult, operatorConfigResult, logsResult, candidatesResult, eventsResult] = optional;
        setOverview(overviewPayload);
        const nextPositions = positionsPayload.positions || [];
        setPositions(nextPositions);
        if (readinessResult.status === "fulfilled") setReadiness(readinessResult.value);
        if (freshnessResult.status === "fulfilled") setFreshness(freshnessResult.value);
        if (tradesResult.status === "fulfilled") setTrades(tradesResult.value);
        if (decisionsResult.status === "fulfilled") setDecisions(decisionsResult.value);
        if (paperReviewResult.status === "fulfilled") setPaperReview(paperReviewResult.value);
        if (winnerPatternsResult.status === "fulfilled") setWinnerPatterns(winnerPatternsResult.value);
        if (watchlistResult.status === "fulfilled") setWatchlist(watchlistResult.value);
        if (walletsResult.status === "fulfilled") {
          const walletsPayload = walletsResult.value;
          setWallets(walletsPayload);
          setSelectedWallet((current) => {
            if (current && (walletsPayload.wallets || []).some((wallet) => wallet.wallet === current)) return current;
            return walletsPayload.wallets?.[0]?.wallet || "";
          });
        }
        if (candidateWalletsResult.status === "fulfilled") setCandidateWallets(candidateWalletsResult.value);
        if (walletLifecycleResult.status === "fulfilled") setWalletLifecycle(walletLifecycleResult.value);
        if (walletApplyResult.status === "fulfilled") setWalletApply(walletApplyResult.value);
        if (operatorConfigResult.status === "fulfilled") setOperatorConfig(operatorConfigResult.value);
        if (logsResult.status === "fulfilled") setLogs(logsResult.value);
        if (candidatesResult.status === "fulfilled") setCandidates(candidatesResult.value);
        if (eventsResult.status === "fulfilled") setEvents(eventsResult.value);
        const candidateMints = candidatesResult.status === "fulfilled"
          ? new Set((candidatesResult.value.items || []).map((item) => item.mint).filter(Boolean))
          : new Set<string>();
        const eventMints = eventsResult.status === "fulfilled"
          ? new Set((eventsResult.value.items || []).map((item) => item.mint || "").filter(Boolean))
          : new Set<string>();
        setApiStatus((current) => ({
          running: true,
          started: current?.started || false,
          detail: current?.started ? "desktop API started in read-only mode" : "desktop API already running in read-only mode",
        }));
        setSelectedMint((current) => {
          if (current && nextPositions.some((position) => position.mint === current)) return current;
          if (current && candidateMints.has(current)) return current;
          if (current && eventMints.has(current)) return current;
          return nextPositions[0]?.mint || "";
        });
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          const message = loadError instanceof Error ? loadError.message : "Unknown desktop API error";
          setError(message);
          setApiStatus((current) => current || { running: false, started: false, detail: message });
        }
      } finally {
        inFlight = false;
      }
    }
    load();
    const timer = window.setInterval(load, OVERVIEW_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedMint) {
      setTokenDetail(null);
      setCandles(null);
      setSnapshots(null);
      setTokenError("");
      return;
    }
    let cancelled = false;
    let inFlight = false;
    setTokenError("");
    async function loadSelected() {
      if (inFlight) return;
      inFlight = true;
      try {
        const tokenState = await loadTokenState(selectedMint, chartMetric, candleInterval);
        if (cancelled) return;
        setTokenDetail(tokenState.detail);
        setCandles(tokenState.candles);
        setSnapshots(tokenState.snapshots);
        setTokenError("");
      } catch (loadError) {
        if (!cancelled) {
          setTokenError(loadError instanceof Error ? loadError.message : "Unknown selected-token error");
          setTokenDetail(null);
          setCandles(null);
          setSnapshots(null);
        }
      } finally {
        inFlight = false;
      }
    }
    loadSelected();
    const timer = window.setInterval(loadSelected, SELECTED_TOKEN_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedMint, chartMetric, candleInterval]);

  useEffect(() => {
    if (!selectedWallet) {
      setWalletDetail(null);
      return;
    }
    let cancelled = false;
    let inFlight = false;
    async function loadWallet() {
      if (inFlight) return;
      inFlight = true;
      try {
        const detail = await fetchJson<WalletDetailPayload>(walletDetailApiPath(selectedWallet));
        if (!cancelled) setWalletDetail(detail);
      } catch {
        if (!cancelled) setWalletDetail(null);
      } finally {
        inFlight = false;
      }
    }
    loadWallet();
    const timer = window.setInterval(loadWallet, OVERVIEW_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedWallet]);

  const selected = positions.find((position) => position.mint === selectedMint);
  const runtimeState = overview?.runtime?.state || "connecting";
  const protection = tokenDetail?.protection;
  const signals = tokenDetail?.signals;
  const selectedTrade = findTradeForMint(trades, selectedMint || selected?.mint || "");
  const overviewLoaded = overview !== null;
  const readinessLoaded = readiness !== null;
  const freshnessLoaded = freshness !== null;
  const tradesLoaded = trades !== null;
  const decisionsLoaded = decisions !== null;
  const selectedTokenLoading = Boolean(selectedMint && !tokenDetail && !tokenError);
  const handleProtectedAmountSaved = (item: WatchlistItem) => {
    const mint = item.token_mint || item.mint || "";
    setWatchlist((current) => {
      if (!current || !mint) return current;
      const items = current.items || [];
      const index = items.findIndex((row) => (row.token_mint || row.mint || "") === mint && (row.wallet || "") === (item.wallet || ""));
      const nextItems = index >= 0
        ? items.map((row, rowIndex) => rowIndex === index ? { ...row, ...item } : row)
        : [...items, item];
      return { ...current, items: nextItems, count: nextItems.length };
    });
  };

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <strong>MemeTraderPro</strong>
            <small>Tauri shell spike</small>
          </div>
        </div>
        <nav className="topnav">
          {(["cockpit", "portfolio", "details", "protection", "wallets", "signals", "replay", "ops", "system"] as WorkArea[]).map((area) => (
            <button className={workArea === area ? "active" : ""} key={area} onClick={() => setWorkArea(area)}>
              {area}
            </button>
          ))}
        </nav>
        <div className={`status ${runtimeState === "online" ? "online" : "stale"}`}>{runtimeState}</div>
      </header>

      <section className="hero">
        <div>
          <p className="eyebrow">Read-only desktop cockpit</p>
          <h1>{selected?.label || (events?.items?.length ? "Scanner activity live" : "Waiting for local state")}</h1>
          <p>{selected ? `${shortMint(selected.mint)} | ${selected.source} | ${selected.status}` : (events?.items?.length ? `${events.count} recent wallet events. Candidates/trades appear only after filters pass.` : "Start the desktop API to populate local state.")}</p>
        </div>
        <div className="lock-card">
          <span>Live execution</span>
          <strong>{overview?.live_execution_locked === false ? "UNLOCKED" : "LOCKED"}</strong>
        </div>
        <div className="lock-card api-card">
          <span>Local API</span>
          <strong>{apiStatus?.running ? (apiStatus.started ? "STARTED" : "RUNNING") : "CHECKING"}</strong>
          <small>{apiStatus?.detail || "Checking local read-only API..."}</small>
        </div>
      </section>

      {error ? <section className="error">Desktop API error: {error}</section> : null}

      {workArea === "cockpit" ? <section className="grid">
        <div className="panel positions">
          <h2>Positions</h2>
          <div className="position-table-head">
            <span>Token</span>
            <span>Risk</span>
            <span>PNL</span>
          </div>
          {!overviewLoaded ? <LoadingState title="Loading positions" detail="Reading paper and protected position state." rows={4} /> : positions.length ? positions.map((position) => (
            <button
              className={position.mint === selected?.mint ? "position position-grid active" : "position position-grid"}
              key={position.mint}
              onClick={() => setSelectedMint(position.mint)}
            >
              <span><strong>{position.label || shortMint(position.mint)}</strong><small>{position.source}</small></span>
              <span>{position.risk_level || position.alert_level || position.status || "-"}</span>
              <span>{pct(position.pnl_pct)}</span>
            </button>
          )) : <EmptyState title="No active positions" detail="Open paper trades or protected manual tokens will appear here." />}
        </div>

        <div className="panel selected">
          <h2>Selected Token</h2>
          {!overviewLoaded ? <LoadingState title="Loading token cockpit" detail="Starting local API and loading selected-token state." /> : (
            <>
              <div className="metrics">
                <div><span>Price</span><strong>{price(selected?.price)}</strong></div>
                <div><span>Market Cap</span><strong>{money(selected?.market_cap ?? tokenDetail?.position?.market_cap ?? tokenDetail?.latest_snapshot?.market_info?.market_cap)}</strong></div>
                <div><span>Liquidity</span><strong>{money(selected?.liquidity)}</strong></div>
                <div><span>Risk</span><strong>{selected?.risk_level || selected?.alert_level || (selectedTokenLoading ? "LOADING" : "UNKNOWN")}</strong></div>
              </div>
              <div className="chart-toolbar">
                <div className="segmented-control" aria-label="Chart metric">
                  <button type="button" className={chartMetric === "price" ? "active" : ""} onClick={() => setChartMetric("price")}>Price</button>
                  <button type="button" className={chartMetric === "liquidity" ? "active" : ""} onClick={() => setChartMetric("liquidity")}>Liquidity</button>
                </div>
                <div className="segmented-control" aria-label="Candle interval">
                  {CANDLE_INTERVALS.map((interval) => (
                    <button
                      type="button"
                      key={interval.value}
                      className={candleInterval === interval.value ? "active" : ""}
                      onClick={() => setCandleInterval(interval.value)}
                    >
                      {interval.label}
                    </button>
                  ))}
                </div>
                <span>{selectedTokenLoading ? "loading snapshots" : `${candles?.snapshot_count ?? 0} snapshots`}</span>
              </div>
              <TradingChart payload={candles} metric={chartMetric} />
            </>
          )}
          {tokenError ? <div className="inline-error">Selected token error: {tokenError}</div> : null}
        </div>

        <PositionMonitor position={selected} detail={tokenDetail} snapshots={snapshots} />
      </section> : null}

      {workArea === "cockpit" ? <>
        <LiveWalletActivity events={events} onSelectMint={setSelectedMint} />
        <LiveLaunchFeed candidates={candidates} onSelectMint={setSelectedMint} />
      </> : null}

      {workArea === "portfolio" ? <PortfolioPanel trades={trades} winnerPatterns={winnerPatterns} loaded={tradesLoaded} onSelectMint={setSelectedMint} /> : null}

      {workArea === "protection" ? <ProtectionDrilldown selectedMint={selectedMint} detail={tokenDetail} watchlist={watchlist} onSelectMint={setSelectedMint} onProtectedAmountSaved={handleProtectedAmountSaved} /> : null}

      {workArea === "wallets" ? <WalletIntelligence wallets={wallets} candidateWallets={candidateWallets} walletLifecycle={walletLifecycle} walletApply={walletApply} selectedWallet={selectedWallet} detail={walletDetail} onSelectWallet={setSelectedWallet} onWalletApply={setWalletApply} /> : null}

      {workArea === "ops" ? <OpsPanel config={operatorConfig} logs={logs} /> : null}

      {workArea === "cockpit" ? <section className="detail-grid">
        <LockedActions />

        <WalletConfidenceSummary confidence={overview?.wallet_confidence} />

        <div className="panel">
          <h2>Protection Rail</h2>
          {selectedTokenLoading ? <LoadingState title="Loading protection state" detail="Checking local watchdog and selected-token snapshots." rows={2} /> : (
            <>
              <div className="rail-status">
                <span>{protection?.state || "NO POSITION"}</span>
                <strong>{protection?.risk_level || protection?.alert_level || "NO DATA"}</strong>
              </div>
              <div className="mini-grid">
                <div><span>Quote</span><strong>{protection?.quote_status || "-"}</strong></div>
                <div><span>Sell Plan</span><strong>{protection?.suggested_sell_pct ? `${protection.suggested_sell_pct}%` : "-"}</strong></div>
                <div><span>Auto Sell</span><strong>LOCKED</strong></div>
                <div><span>Live Action</span><strong>LOCKED</strong></div>
                <div><span>Price Peak</span><strong>{pct(protection?.price_from_peak_pct)}</strong></div>
                <div><span>Liq Peak</span><strong>{pct(protection?.liquidity_from_peak_pct)}</strong></div>
              </div>
              <p className="muted">{protection?.token_standard || "Token standard unknown"} | {(protection?.token_extensions || []).join(", ") || "no extension data"}</p>
              {(protection?.reasons || []).slice(0, 3).map((reason) => <p className="note" key={reason}>{reason}</p>)}
            </>
          )}
        </div>

        <div className="panel">
          <h2>Signal Rail</h2>
          {signals?.catalysts?.length || signals?.social?.length ? (
            <>
              {(signals.catalysts || []).map((item) => (
                <div className="note-card catalyst" key={`${item.mint}-${item.summary}`}>
                  <strong>{item.symbol || shortMint(item.mint)}</strong>
                  <p>{item.summary || "Catalyst card"}</p>
                </div>
              ))}
              {(signals.social || []).map((item) => (
                <div className="note-card social" key={`${item.account}-${item.text}`}>
                  <strong>{item.account || "social"}</strong>
                  <p>{item.text || "No text"}</p>
                  <small>{(item.keywords || []).join(", ")}</small>
                </div>
              ))}
            </>
          ) : <p className="muted">No direct local signal match for this selected mint.</p>}
        </div>

        <div className="panel">
          <h2>Snapshot Feed</h2>
          {selectedTokenLoading ? <LoadingState title="Loading snapshot feed" detail="Waiting for selected-token snapshots." rows={4} /> : (snapshots?.snapshots || []).slice(-8).reverse().map((snapshot, index) => (
            <div className="snapshot" key={`${snapshot.time}-${snapshot.context}-${index}`}>
              <strong>{snapshot.context || "snapshot"}</strong>
              <small>{snapshot.source || "-"} | {price(snapshot.price)} | {money(snapshot.liquidity)}</small>
            </div>
          ))}
          {!selectedTokenLoading && !(snapshots?.snapshots || []).length ? <EmptyState title="No snapshots yet" detail="Token snapshots will appear after scanner, paper, or watchdog writes state." /> : null}
        </div>

        <TradeLifecycle trade={selectedTrade} />
      </section> : null}

      {workArea === "details" ? <TokenDetail detail={tokenDetail} /> : null}

      {workArea === "signals" ? <section className="detail-grid wide">
        <LiveWalletActivity events={events} onSelectMint={setSelectedMint} expanded />
        <LiveLaunchFeed candidates={candidates} onSelectMint={setSelectedMint} expanded />
        <SocialImportPanel selectedMint={selectedMint} selectedLabel={selected?.label || tokenDetail?.position?.label || ""} />
        <div className="panel">
          <h2>Selected Catalyst Matches</h2>
          {(signals?.catalysts || []).map((item) => (
            <div className="note-card catalyst" key={`${item.mint}-${item.summary}`}>
              <strong>{item.symbol || shortMint(item.mint)}</strong>
              <p>{item.summary || "Catalyst card"}</p>
              <small>{(item.sources || []).join(", ") || "local"} | {item.snapshot_count ?? 0} snapshots</small>
            </div>
          ))}
          {signals?.catalysts?.length ? null : <p className="muted">No selected-token catalyst card match.</p>}
        </div>
        <div className="panel">
          <h2>Selected Social Matches</h2>
          {(signals?.social || []).map((item) => (
            <div className="note-card social" key={`${item.account}-${item.text}`}>
              <strong>{item.account || "social"}</strong>
              <p>{item.text || "No text"}</p>
              <small>{(item.keywords || []).join(", ")}</small>
            </div>
          ))}
          {signals?.social?.length ? null : <p className="muted">No selected-token social match.</p>}
        </div>
        <div className="panel">
          <h2>Signal Counts</h2>
          <div className="mini-grid">
            <div><span>Social</span><strong>{signals?.social_count ?? 0}</strong></div>
            <div><span>Catalysts</span><strong>{signals?.catalyst_count ?? 0}</strong></div>
            <div><span>Latest Source</span><strong>{tokenDetail?.trend?.latest_source || "-"}</strong></div>
            <div><span>Latest Context</span><strong>{tokenDetail?.trend?.latest_context || "-"}</strong></div>
          </div>
        </div>
      </section> : null}

      {workArea === "replay" ? <section className="detail-grid wide replay-grid">
        <DecisionLedger decisions={decisions} loaded={decisionsLoaded} onSelectMint={setSelectedMint} />
        <PaperReviewPanel review={paperReview} loaded={tradesLoaded} />
        <ReplayPanel title="Open Paper Trades" trades={trades?.open_trades || []} loaded={tradesLoaded} empty="No open paper trades." />
        <ReplayPanel title="Closed Trades" trades={trades?.closed_trades || []} loaded={tradesLoaded} empty="No closed paper trades." />
        <ReplayPanel title="Failed Trades" trades={trades?.failed_trades || []} loaded={tradesLoaded} empty="No failed paper trades." />
      </section> : null}

      {workArea === "system" ? <section className="detail-grid wide">
        <div className="panel">
          <h2>System Readiness</h2>
          <div className="rail-status neutral">
            <span>Overall</span>
            <strong>{readinessLoaded ? readiness?.overall || "NO DATA" : "LOADING"}</strong>
          </div>
          <div className="mini-grid">
            <div><span>OK</span><strong>{readinessLoaded ? readiness?.counts?.OK ?? 0 : "-"}</strong></div>
            <div><span>WARN</span><strong>{readinessLoaded ? readiness?.counts?.WARN ?? 0 : "-"}</strong></div>
            <div><span>FAIL</span><strong>{readinessLoaded ? readiness?.counts?.FAIL ?? 0 : "-"}</strong></div>
            <div><span>Mode</span><strong>{overview?.mode || "-"}</strong></div>
          </div>
        </div>
        <div className="panel">
          <h2>Readiness Checks</h2>
          {!readinessLoaded ? <LoadingState title="Loading readiness checks" detail="Reading local runtime and storage preflight state." /> : (readiness?.rows || []).slice(0, 12).map((row) => (
            <div className="snapshot" key={row.check}>
              <strong>{row.check}: {row.status}</strong>
              <small>{row.detail}</small>
            </div>
          ))}
          {readinessLoaded && !(readiness?.rows || []).length ? <EmptyState title="No readiness checks" detail="Readiness rows were not present in the desktop API payload." /> : null}
        </div>
        <div className="panel">
          <h2>SQLite Store</h2>
          {!readinessLoaded ? <LoadingState title="Loading SQLite counts" detail="Reading local store counts." rows={2} /> : (
            <div className="mini-grid">
              {Object.entries(readiness?.sqlite_counts || {}).map(([key, value]) => (
                <div key={key}><span>{key}</span><strong>{value}</strong></div>
              ))}
            </div>
          )}
        </div>
        <div className="panel system-wide">
          <h2>Data Freshness</h2>
          <div className="rail-status neutral">
            <span>Overall</span>
            <strong>{freshnessLoaded ? freshness?.freshness?.overall || "NO DATA" : "LOADING"}</strong>
          </div>
          {!freshnessLoaded ? <LoadingState title="Loading data freshness" detail="Checking JSON, SQLite, and runtime source ages." rows={4} /> : <div className="mini-grid">
              {Object.entries(freshness?.freshness?.counts || {}).map(([key, value]) => (
                <div key={key}><span>{key}</span><strong>{value}</strong></div>
              ))}
            </div>}
          {freshnessLoaded && (freshness?.freshness?.rows || []).map((row) => (
            <div className="source-row" key={row.source}>
              <div>
                <strong>{row.source}</strong>
                <small>{row.path} | {row.owner || "local"} | {row.detail || "-"}</small>
              </div>
              <span className={statusTone(row.status)}>{row.status}</span>
              <small>{row.age}</small>
            </div>
          ))}
          {freshnessLoaded && !(freshness?.freshness?.rows || []).length ? <EmptyState title="No freshness rows" detail="Freshness data was not present in the desktop API payload." /> : null}
        </div>
      </section> : null}
    </main>
  );
}

function statusTone(status: string): string {
  const normalized = String(status || "").toUpperCase();
  if (["OK", "FRESH"].includes(normalized)) return "good-pill";
  if (["MISSING", "BROKEN", "FAIL", "OLD"].includes(normalized)) return "bad-pill";
  return "warn-pill";
}

function WalletConfidenceSummary({ confidence }: { confidence?: OperatorWalletConfidence }) {
  const labels = Object.entries(confidence?.top_labels || {}).slice(0, 4);
  const wallets = confidence?.wallets || [];
  return (
    <div className="panel wallet-confidence-summary">
      <h2>Wallet Confidence</h2>
      <div className="mini-grid">
        <div><span>Wallets</span><strong>{confidence?.wallet_count ?? 0}</strong></div>
        <div><span>Signals</span><strong>{confidence?.signal_count ?? 0}</strong></div>
        <div><span>Tokens</span><strong>{confidence?.token_count ?? 0}</strong></div>
        <div><span>Open Drivers</span><strong>{confidence?.open_trade_wallets ?? 0}</strong></div>
        <div><span>Proven</span><strong className={(confidence?.proven_wallets || 0) ? "good" : ""}>{confidence?.proven_wallets ?? 0}</strong></div>
        <div><span>Trap Risk</span><strong className={(confidence?.trap_wallets || 0) ? "bad" : ""}>{confidence?.trap_wallets ?? 0}</strong></div>
      </div>
      <div className="confidence-score-row">
        <span>Average score</span>
        <strong>{score(confidence?.avg_score)}</strong>
      </div>
      {labels.length ? (
        <div className="confidence-labels">
          {labels.map(([label, count]) => <span key={label}>{label} {count}</span>)}
        </div>
      ) : null}
      <div className="confidence-wallets">
        {wallets.slice(0, 3).map((wallet) => (
          <div key={wallet.wallet}>
            <strong>{shortMint(wallet.wallet)}</strong>
            <small>{score(wallet.score)} score | {money(wallet.avg_pnl)} avg | {wallet.postmortem?.closed_trades ?? 0}/{wallet.postmortem?.failed_trades ?? 0} outcomes</small>
          </div>
        ))}
        {wallets.length ? null : <p className="muted">No recent wallet confidence data yet.</p>}
      </div>
    </div>
  );
}

function score(value: number | undefined): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) : "-";
}

function SocialImportPanel({ selectedMint, selectedLabel }: { selectedMint: string; selectedLabel: string }) {
  const [account, setAccount] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const canSubmit = Boolean(text.trim()) && !saving;

  async function submitSocial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setStatus("");
    setError("");
    try {
      const response = await importSocialPost({
        mint: selectedMint || undefined,
        account: account.trim() || undefined,
        text: text.trim(),
      });
      setStatus(response.detail || "Social item imported for signal matching.");
      setText("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to import social item.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="panel social-import-panel" onSubmit={submitSocial}>
      <div className="candidate-feed-head">
        <div>
          <h2>Social / Tweet Import</h2>
          <p className="muted">{selectedMint ? `Posts with ${selectedLabel || shortMint(selectedMint)} context to /api/social/import.` : "Posts to /api/social/import without selected-token context."}</p>
        </div>
        <span>{selectedMint ? shortMint(selectedMint) : "no token"}</span>
      </div>
      <label>
        <span>Account</span>
        <input
          value={account}
          onChange={(event) => setAccount(event.target.value)}
          placeholder="@account or source"
          autoComplete="off"
        />
      </label>
      <label>
        <span>Tweet / Social Text</span>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Paste a social post to import into local signal matching."
          rows={5}
        />
      </label>
      <button type="submit" disabled={!canSubmit}>{saving ? "Importing" : "Import Social"}</button>
      {status ? <p className="note good-note">{status}</p> : null}
      {error ? <p className="note danger-note">{error}</p> : null}
    </form>
  );
}

function LiveWalletActivity({ events, onSelectMint, expanded = false }: {
  events: EventFeedPayload | null;
  onSelectMint: (mint: string) => void;
  expanded?: boolean;
}) {
  const items = events?.items || [];
  const visible = expanded ? items.slice(0, 36) : items.slice(0, 14);
  return (
    <section className={expanded ? "event-feed expanded panel" : "event-feed panel"}>
      <div className="candidate-feed-head">
        <div>
          <h2>Scanner Tape</h2>
          <p className="muted">Raw tracked-wallet buys and sells before strategy filters.</p>
        </div>
        <span>{events ? `${events.count} recent` : "loading"}</span>
      </div>
      {!events ? <LoadingState title="Loading scanner tape" detail="Reading recent wallet events." rows={4} /> : null}
      {events && !visible.length ? <EmptyState title="No wallet activity yet" detail="Tracked-wallet buy and sell events will appear here even before a token becomes a candidate." /> : null}
      {visible.length ? <div className="event-table">
        {visible.map((item, index) => (
          <button
            className={`event-row ${eventTypeClass(item.type)}`}
            key={`${item.time}-${item.wallet}-${item.mint}-${index}`}
            onClick={() => item.mint ? onSelectMint(item.mint) : undefined}
            disabled={!item.mint}
          >
            <EventTokenImage item={item} />
            <span className="event-side">{String(item.type || "event").toUpperCase()}</span>
            <span><strong>{item.symbol || item.name || shortMint(item.mint || "")}</strong><small>{item.name || `${shortMint(item.mint || "")} | ${formatAge(item.age_seconds)}`}</small></span>
            <span><strong>{shortMint(item.wallet || "")}</strong><small>wallet</small></span>
            <span><strong>{money(item.market_cap)}</strong><small>MC</small></span>
            <span><strong>{money(item.liquidity)}</strong><small>Liq</small></span>
            <span><strong>{formatTokenAmount(item.amount)}</strong><small>amount</small></span>
            <span><strong>{formatScore(item.combined_wallet_score)}</strong><small>score</small></span>
          </button>
        ))}
      </div> : null}
    </section>
  );
}

function EventTokenImage({ item }: { item: EventFeedItem }) {
  if (item.image_url) {
    return <img className="event-image" src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />;
  }
  const label = (item.symbol || item.name || item.mint || "?").slice(0, 2).toUpperCase();
  return <span className="event-image placeholder">{label}</span>;
}

function LiveLaunchFeed({ candidates, onSelectMint, expanded = false }: {
  candidates: CandidateFeedPayload | null;
  onSelectMint: (mint: string) => void;
  expanded?: boolean;
}) {
  const items = candidates?.items || [];
  const visible = expanded ? items.slice(0, 18) : items.slice(0, 10);
  return (
    <section className={expanded ? "candidate-feed expanded panel" : "candidate-feed panel"}>
      <div className="candidate-feed-head">
        <div>
          <h2>Live Launch Feed</h2>
          <p className="muted">Recent scanner candidates, including skipped tokens.</p>
        </div>
        <span>{candidates ? `${candidates.count} recent` : "loading"}</span>
      </div>
      {!candidates ? <LoadingState title="Loading launch feed" detail="Reading recent scanner snapshots." rows={4} /> : null}
      {candidates && !visible.length ? <EmptyState title="No scanner candidates yet" detail="Newly scanned launches will appear here with image, market, tx, and decision data." /> : null}
      {visible.map((item) => (
        <button className={`candidate-card ${candidateStatusClass(item.status)}`} key={`${item.mint}-${item.time}`} onClick={() => onSelectMint(item.mint)}>
          <TokenImage item={item} />
          <div className="candidate-main">
            <div className="candidate-title">
              <strong>{item.symbol || item.name || shortMint(item.mint)}</strong>
              <span>{item.status}</span>
            </div>
            <small>{item.name || shortMint(item.mint)} | {formatAge(item.age_seconds)} | {item.context || "scanner"}</small>
            <div className="candidate-reason">{(item.reasons || [])[0] || "No decision reason recorded yet."}</div>
          </div>
          <div className="candidate-stats">
            <span><b>{money(item.market_cap)}</b><small>{item.market_cap_estimated ? "Est. MC" : "MC"}</small></span>
            <span><b>{money(item.liquidity)}</b><small>Liq</small></span>
            <span><b>{item.tx_count ?? "-"}</b><small>Tx</small></span>
            <span><b>{item.holder_count ?? "-"}</b><small>Holders</small></span>
          </div>
        </button>
      ))}
    </section>
  );
}

function TokenImage({ item }: { item: CandidateFeedItem }) {
  if (item.image_url) {
    return <img className="candidate-image" src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer" />;
  }
  const label = (item.symbol || item.name || item.mint || "?").slice(0, 2).toUpperCase();
  return <span className="candidate-image placeholder">{label}</span>;
}

function candidateStatusClass(status?: string) {
  const normalized = String(status || "").toLowerCase();
  if (normalized.includes("ready")) return "ready";
  if (normalized.includes("block")) return "blocked";
  return "skipped";
}

function eventTypeClass(type?: string) {
  const normalized = String(type || "").toLowerCase();
  if (normalized.includes("buy")) return "buy";
  if (normalized.includes("sell")) return "sell";
  return "neutral";
}

function formatAge(age?: number | null) {
  if (age === null || age === undefined || Number.isNaN(age)) return "age unknown";
  if (age < 60) return `${Math.round(age)}s`;
  if (age < 3600) return `${Math.round(age / 60)}m`;
  return `${Math.round(age / 3600)}h`;
}

function formatTokenAmount(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const numeric = Number(value);
  if (Math.abs(numeric) >= 1_000_000) return `${(numeric / 1_000_000).toFixed(1)}M`;
  if (Math.abs(numeric) >= 1_000) return `${(numeric / 1_000).toFixed(1)}K`;
  if (Math.abs(numeric) >= 1) return numeric.toFixed(2);
  return numeric.toPrecision(3);
}

function formatScore(value?: number | null) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(1);
}

function PaperReviewPanel({ review, loaded }: { review: PaperReviewPayload | null; loaded: boolean }) {
  const metrics = review?.metrics;
  const mainLane = review?.lane_metrics?.main;
  const explorationLane = review?.lane_metrics?.exploration;
  const progress = metrics ? Math.min(100, Math.round((metrics.closed_trades / review.minimum_closed_trades) * 100)) : 0;
  return (
    <div className="panel paper-review-panel">
      <div className="paper-review-head">
        <div>
          <h2>Paper Profitability Review</h2>
          <p className="muted">{review?.main_meaningful_test_ready ? "Main strategy sample ready" : "Collecting main-strategy sample before judging profitability"}</p>
        </div>
        <span className={review?.main_meaningful_test_ready ? "good-pill" : "warn-pill"}>{review?.main_meaningful_test_ready ? "READY" : "NOT READY"}</span>
      </div>
      {!loaded || !review || !metrics ? <LoadingState title="Loading paper review" detail="Analyzing paper trades, exits, failures, and wallet labels." rows={4} /> : (
        <>
          <div className="paper-progress">
            <div><span style={{ width: `${progress}%` }} /></div>
            <small>{metrics.closed_trades} / {review.minimum_closed_trades} minimum closed trades | {review.recommended_closed_trades} recommended</small>
          </div>
          <div className="mini-grid">
            <div><span>Closed</span><strong>{metrics.closed_trades}</strong></div>
            <div><span>Failed</span><strong>{metrics.failed_trades}</strong></div>
            <div><span>Win Rate</span><strong>{pct(metrics.win_rate)}</strong></div>
            <div><span>Total PnL</span><strong className={metrics.total_pnl >= 0 ? "good" : "bad"}>{money(metrics.total_pnl)}</strong></div>
            <div><span>Expectancy</span><strong className={metrics.expectancy >= 0 ? "good" : "bad"}>{money(metrics.expectancy)}</strong></div>
            <div><span>Profit Factor</span><strong>{metrics.profit_factor == null ? "-" : metrics.profit_factor.toFixed(2)}</strong></div>
          </div>
          <div className="lane-grid">
            <div>
              <span>Main Strategy</span>
              <strong>{mainLane?.closed_trades ?? 0} closed</strong>
              <small>{money(mainLane?.realized_pnl ?? 0)} realized | {pct(mainLane?.win_rate ?? 0)} wins</small>
            </div>
            <div>
              <span>Exploration Lane</span>
              <strong>{explorationLane?.closed_trades ?? 0} closed</strong>
              <small>{money(explorationLane?.realized_pnl ?? 0)} realized | {pct(explorationLane?.win_rate ?? 0)} wins</small>
            </div>
          </div>
          <ReviewList title="Readiness Gaps" rows={review.readiness_gaps} empty="No readiness gaps. This sample is large enough for a meaningful paper review." />
          <ReviewPairs title="Entry Reasons" rows={review.entry_reasons} />
          <ReviewPairs title="Exit Reasons" rows={review.exit_reasons} />
          <ReviewPairs title="Failure Reasons" rows={review.failure_reasons} />
          <ReviewPairs title="Wallet Label Exposure" rows={review.wallet_label_exposure} />
          <ReviewList title="Next Review Actions" rows={review.next_review_actions} empty="No review actions recorded." />
        </>
      )}
    </div>
  );
}

function ReviewList({ title, rows, empty }: { title: string; rows: string[]; empty: string }) {
  return (
    <div className="review-block">
      <strong>{title}</strong>
      {rows.length ? rows.slice(0, 5).map((row) => <p key={row}>{row}</p>) : <p>{empty}</p>}
    </div>
  );
}

function ReviewPairs({ title, rows }: { title: string; rows: Record<string, number> }) {
  const entries = Object.entries(rows || {}).slice(0, 6);
  return (
    <div className="review-block">
      <strong>{title}</strong>
      {entries.length ? entries.map(([key, value]) => <p key={key}>{key}: {value}</p>) : <p>None recorded.</p>}
    </div>
  );
}

function PortfolioPanel({ trades, winnerPatterns, loaded, onSelectMint }: { trades: TradesPayload | null; winnerPatterns: WinnerPatternPayload | null; loaded: boolean; onSelectMint: (mint: string) => void }) {
  const summary = summarizeTrades(trades);
  const openTrades = trades?.open_trades || [];
  const closedTrades = trades?.closed_trades || [];
  const failedTrades = trades?.failed_trades || [];
  const [selectedTradeKey, setSelectedTradeKey] = useState("");
  const allTrades = [...openTrades, ...closedTrades, ...failedTrades];
  const selectedTrade = findPortfolioTrade(allTrades, selectedTradeKey) || allTrades[0] || null;
  useEffect(() => {
    if (!selectedTradeKey && allTrades.length) {
      setSelectedTradeKey(portfolioTradeKey(allTrades[0], 0));
    }
  }, [allTrades, selectedTradeKey]);
  return (
    <section className="portfolio-view">
      <div className="panel portfolio-summary-panel">
        <div className="portfolio-head">
          <div>
            <h2>Portfolio PnL</h2>
            <p className="muted">Paper-trade ledger totals from open and closed positions.</p>
          </div>
          <strong className={`portfolio-total ${pnlTone(summary.totalPnl)}`}>{pnlMoney(summary.totalPnl)}</strong>
        </div>
        <div className="portfolio-summary-grid">
          <PortfolioMetric label="Open PnL" value={pnlMoney(summary.openPnl)} tone={pnlTone(summary.openPnl)} />
          <PortfolioMetric label="Closed PnL" value={pnlMoney(summary.closedPnl)} tone={pnlTone(summary.closedPnl)} />
          <PortfolioMetric label="Open Trades" value={String(summary.openCount)} />
          <PortfolioMetric label="Closed Trades" value={String(summary.closedCount)} />
          <PortfolioMetric label="Failed Attempts" value={String(summary.failedCount)} tone={summary.failedCount ? "warn" : undefined} />
        </div>
      </div>
      <WinnerPatternPanel review={winnerPatterns} />
      <PortfolioTradeDetail trade={selectedTrade} loaded={loaded} />
      <TradeLedger title="Open Positions" trades={openTrades} loaded={loaded} empty="No open paper positions." onSelectMint={onSelectMint} selectedKey={selectedTradeKey} onSelectTrade={setSelectedTradeKey} mode="open" />
      <TradeLedger title="Closed Trades" trades={closedTrades} loaded={loaded} empty="No closed paper trades yet." onSelectMint={onSelectMint} selectedKey={selectedTradeKey} onSelectTrade={setSelectedTradeKey} mode="closed" />
      <TradeLedger title="Failed Attempts" trades={failedTrades} loaded={loaded} empty="No failed paper attempts." onSelectMint={onSelectMint} selectedKey={selectedTradeKey} onSelectTrade={setSelectedTradeKey} mode="failed" />
    </section>
  );
}

function WinnerPatternPanel({ review }: { review: WinnerPatternPayload | null }) {
  return (
    <div className="panel winner-pattern-panel">
      <div className="ledger-title">
        <h2>Winner Pattern Review</h2>
        <span>{review ? `${review.winner_count} winners / ${review.loser_count} losers` : "loading"}</span>
      </div>
      {!review ? <LoadingState title="Loading winner pattern review" detail="Comparing closed winners against closed losers." rows={3} /> : (
        <>
          {review.sample_warning ? <p className="note danger-note">{review.sample_warning}</p> : null}
          <div className="portfolio-summary-grid winner-grid">
            <PortfolioMetric label="Big Winners" value={String(review.big_winner_count)} />
            <PortfolioMetric label="Repeatable Traits" value={String(review.repeatable_traits.length)} />
            <PortfolioMetric label="Top Wallets" value={String(review.wallet_leaders.length)} />
            <PortfolioMetric label="Live Execution" value={review.live_execution_locked ? "LOCKED" : "UNLOCKED"} tone={review.live_execution_locked ? "good" : "bad"} />
          </div>
          <div className="winner-review-grid">
            <div>
              <strong>Traits To Watch</strong>
              {(review.repeatable_traits || []).length ? review.repeatable_traits.map((trait) => (
                <p key={trait}>{trait}: {review.trait_counts?.[trait] ?? 0}</p>
              )) : <p>No repeatable winner traits yet.</p>}
            </div>
            <div>
              <strong>Top Winners</strong>
              {(review.top_winners || []).slice(0, 4).map((trade) => (
                <p key={`${trade.mint}-${trade.pnl}`}>{trade.symbol || shortMint(trade.mint)} | {pnlMoney(trade.pnl)} | MC {money(trade.entry_market_cap)} to {money(trade.exit_market_cap)}</p>
              ))}
              {review.top_winners?.length ? null : <p>No closed winners yet.</p>}
            </div>
            <div>
              <strong>Wallet Leaders</strong>
              {(review.wallet_leaders || []).slice(0, 4).map((wallet) => (
                <p key={wallet.wallet}>{shortMint(wallet.wallet)} | {wallet.wins} wins | {pnlMoney(wallet.pnl)}</p>
              ))}
              {review.wallet_leaders?.length ? null : <p>No winner wallet leaders yet.</p>}
            </div>
            <div>
              <strong>Actions</strong>
              {(review.recommended_actions || []).slice(0, 4).map((action) => <p key={action}>{action}</p>)}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function PortfolioMetric({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

function PortfolioTradeDetail({ trade, loaded }: { trade: TradeRecord | null; loaded: boolean }) {
  if (!loaded) {
    return <div className="panel trade-detail-panel"><LoadingState title="Loading trade detail" detail="Reading selected paper-trade record." rows={3} /></div>;
  }
  if (!trade) {
    return <div className="panel trade-detail-panel"><EmptyState title="No trade selected" detail="Open, closed, or failed paper trades will appear here." /></div>;
  }
  const wallets = (trade.wallets || []).filter(Boolean);
  const sells = Array.isArray(trade.sells) ? trade.sells : [];
  return (
    <div className="panel trade-detail-panel">
      <div className="trade-detail-head">
        <div>
          <h2>Selected Trade Detail</h2>
          <strong>{tradeLabel(trade)}</strong>
          <small>{shortMint(tradeMint(trade))} | {trade.status || "recorded"} | {trade.paper_lane || (trade.exploration ? "exploration" : "main")}</small>
        </div>
        <span className={pnlTone(tradePnl(trade))}>{pnlMoney(tradePnl(trade))}</span>
      </div>
      <div className="trade-detail-grid">
        <PortfolioMetric label="MC In" value={money(tradeMarketCapIn(trade))} />
        <PortfolioMetric label="MC Out / Now" value={money(tradeMarketCapOut(trade))} />
        <PortfolioMetric label="Entry Price" value={price(trade.entry_price ?? trade.quoted_entry_price)} />
        <PortfolioMetric label="Exit / Current Price" value={price(trade.exit_price ?? trade.close_price ?? trade.current_price)} />
        <PortfolioMetric label="Entry Liq" value={money(trade.entry_liquidity_usd ?? trade.liquidity_usd)} />
        <PortfolioMetric label="Current Liq" value={money(trade.current_liquidity_usd ?? trade.liquidity_usd)} />
        <PortfolioMetric label="Size" value={money(tradeSizeUsd(trade))} />
        <PortfolioMetric label="PnL %" value={pct(tradePnlPct(trade))} tone={pnlTone(tradePnlPct(trade) ?? 0)} />
        <PortfolioMetric label="Remaining" value={trade.remaining_pct == null ? "-" : pct(trade.remaining_pct)} />
        <PortfolioMetric label="Fees" value={money(trade.total_fees_usd ?? trade.entry_fee_usd)} />
        <PortfolioMetric label="Opened" value={trade.entry_time_iso || formatTradeTime(trade.entry_time)} />
        <PortfolioMetric label="Closed" value={trade.close_time_iso || trade.exit_time_iso || formatTradeTime(trade.close_time)} />
      </div>
      <div className="trade-detail-notes">
        <div>
          <strong>Entry</strong>
          <p>{trade.entry_reason || trade.reason || "-"}</p>
        </div>
        <div>
          <strong>Exit / Failure</strong>
          <p>{trade.exit_reason || trade.close_reason || trade.failure_reason || "-"}</p>
        </div>
        <div>
          <strong>Wallets</strong>
          <p>{wallets.length ? wallets.map(shortMint).join(", ") : "-"}</p>
        </div>
        <div>
          <strong>Sells</strong>
          <p>{sells.length ? `${sells.length} recorded sell event${sells.length === 1 ? "" : "s"}` : "No sell events recorded."}</p>
        </div>
      </div>
    </div>
  );
}

function TradeLedger({ title, trades, loaded, empty, onSelectMint, selectedKey, onSelectTrade, mode }: { title: string; trades: TradeRecord[]; loaded: boolean; empty: string; onSelectMint: (mint: string) => void; selectedKey: string; onSelectTrade: (key: string) => void; mode: "open" | "closed" | "failed" }) {
  return (
    <div className="panel trade-ledger-panel">
      <div className="ledger-title">
        <h2>{title}</h2>
        <span>{loaded ? `${trades.length} records` : "loading"}</span>
      </div>
      {!loaded ? <LoadingState title={`Loading ${title.toLowerCase()}`} detail="Reading local paper-trade ledger." rows={4} /> : trades.length ? (
        <div className="trade-ledger">
          {trades.slice(0, 40).map((trade, index) => {
            const mint = tradeMint(trade);
            const pnl = tradePnl(trade);
            const pnlPct = tradePnlPct(trade);
            const key = portfolioTradeKey(trade, index);
            return (
              <button className={selectedKey === key ? "trade-ledger-row active" : "trade-ledger-row"} key={key} onClick={() => {
                onSelectTrade(key);
                if (mint) onSelectMint(mint);
              }}>
                <span className="trade-token">
                  <strong>{tradeLabel(trade)}</strong>
                  <small>{shortMint(mint)} | {trade.status || mode}</small>
                </span>
                <span>
                  <small>PnL</small>
                  <strong className={pnlTone(pnl)}>{pnlMoney(pnl)}</strong>
                </span>
                <span>
                  <small>PnL %</small>
                  <strong className={pnlTone(pnlPct ?? 0)}>{pct(pnlPct)}</strong>
                </span>
                <span>
                  <small>Size</small>
                  <strong>{money(tradeSizeUsd(trade))}</strong>
                </span>
                <span>
                  <small>Market Cap</small>
                  <strong>{money(trade.current_market_cap ?? trade.market_cap)}</strong>
                </span>
                <span className="trade-reason">
                  <small>{mode === "failed" ? "Failure" : mode === "closed" ? "Exit" : "Reason"}</small>
                  <strong>{tradeReason(trade)}</strong>
                </span>
              </button>
            );
          })}
        </div>
      ) : <EmptyState title={empty} detail="This section updates automatically when paper trade records exist." />}
    </div>
  );
}

function portfolioTradeKey(trade: TradeRecord, index: number): string {
  return `${trade.status || "recorded"}:${tradeMint(trade)}:${trade.entry_time_iso || trade.close_time_iso || trade.exit_time_iso || index}`;
}

function findPortfolioTrade(trades: TradeRecord[], key: string): TradeRecord | null {
  if (!key) return null;
  return trades.find((trade, index) => portfolioTradeKey(trade, index) === key) || null;
}

function ReplayPanel({ title, trades, loaded, empty }: { title: string; trades: TradeRecord[]; loaded: boolean; empty: string }) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      {!loaded ? <LoadingState title={`Loading ${title.toLowerCase()}`} detail="Reading local paper-trade ledger." rows={3} /> : trades.length ? trades.slice(0, 10).map((trade, index) => (
        <div className="replay-row" key={`${tradeMint(trade)}-${index}`}>
          <div>
            <strong>{tradeLabel(trade)}</strong>
            <small>{shortMint(tradeMint(trade))}</small>
          </div>
          <div>
            <span>PNL</span>
            <strong>{pct(tradePnlPct(trade))}</strong>
          </div>
          <p>{tradeReason(trade)}</p>
          <div className="replay-meta">
            <span>{money(trade.size_usd ?? trade.entry_value)} size</span>
            <span>{money(trade.current_market_cap ?? trade.market_cap)} MC</span>
            <span>{money(trade.current_liquidity_usd ?? trade.liquidity_usd)} liq</span>
          </div>
        </div>
      )) : <EmptyState title={empty} detail="This panel will populate after paper trading records matching this state exist." />}
    </div>
  );
}

function pnlMoney(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "$0.00";
  const sign = numeric < 0 ? "-" : "";
  const absolute = Math.abs(numeric);
  if (absolute >= 1_000_000) return `${sign}$${(absolute / 1_000_000).toFixed(2)}M`;
  if (absolute >= 1_000) return `${sign}$${(absolute / 1_000).toFixed(2)}K`;
  return `${sign}$${absolute.toFixed(2)}`;
}

function pnlTone(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric === 0) return "neutral";
  return numeric > 0 ? "good" : "bad";
}

function formatTradeTime(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  const millis = numeric > 1_000_000_000_000 ? numeric : numeric * 1000;
  return new Date(millis).toLocaleString();
}
