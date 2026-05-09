import { useState } from "react";
import { applyWalletReviewChanges, saveWalletReviewDecision, type CandidateWallet, type CandidateWalletsPayload, type WalletDetailPayload, type WalletLifecyclePayload, type WalletLifecycleRow, type WalletPostmortemTrade, type WalletReviewApplyPayload, type WalletReviewDecisionRequest, type WalletsPayload, type WalletRow, type WalletSignal, type WalletTradeSummary } from "../lib/api";
import { money, pct, shortMint } from "../lib/format";

type Props = {
  wallets: WalletsPayload | null;
  candidateWallets: CandidateWalletsPayload | null;
  walletLifecycle: WalletLifecyclePayload | null;
  walletApply: WalletReviewApplyPayload | null;
  selectedWallet: string;
  detail: WalletDetailPayload | null;
  onSelectWallet: (wallet: string) => void;
  onWalletApply: (payload: WalletReviewApplyPayload) => void;
};

export function WalletIntelligence({ wallets, candidateWallets, walletLifecycle, walletApply, selectedWallet, detail, onSelectWallet, onWalletApply }: Props) {
  const rows = wallets?.wallets || [];
  const selected = detail?.wallet || rows.find((wallet) => wallet.wallet === selectedWallet) || rows[0];
  const signalRows = detail?.recent_signals || wallets?.recent_signals || [];
  const tradeRows = detail?.paper_trades || [];
  const candidateRows = candidateWallets?.candidates || [];
  const lifecycleRows = walletLifecycle?.wallets || [];

  return (
    <section className="wallet-grid">
      <div className="panel wallet-list">
        <h2>Wallet Intelligence</h2>
        {rows.length ? rows.slice(0, 18).map((wallet) => (
          <WalletListRow
            active={wallet.wallet === selected?.wallet}
            wallet={wallet}
            key={wallet.wallet}
            onSelect={onSelectWallet}
          />
        )) : <p className="muted">No wallet performance data loaded.</p>}
      </div>

      <div className="panel wallet-main">
        <h2>Wallet Detail</h2>
        {selected ? (
          <>
            <div className="wallet-title-row">
              <div>
                <strong>{selected.emoji ? `${selected.emoji} ` : ""}{selected.name || shortMint(selected.wallet)}</strong>
                <small>{shortMint(selected.wallet)}</small>
              </div>
              <span>{selected.label || "UNPROVEN"}</span>
            </div>
            <div className="wallet-metric-grid">
              <Metric label="Score" value={score(selected.score)} />
              <Metric label="Signals" value={selected.signals ?? 0} />
              <Metric label="Paper Entries" value={selected.paper_entries ?? 0} />
              <Metric label="Win Rate" value={pct(selected.win_rate_pct)} />
              <Metric label="Avg PnL" value={money(selected.avg_pnl)} tone={tone(selected.avg_pnl)} />
              <Metric label="Best PnL" value={money(selected.best_pnl)} tone="good" />
              <Metric label="Worst PnL" value={money(selected.worst_pnl)} tone="bad" />
              <Metric label="Last Seen" value={age(selected.last_seen_age_seconds)} />
            </div>
            <WalletBehaviorSummary detail={detail} />
            <WalletPostmortemPanel postmortem={detail?.postmortem} />
            <h2 className="subhead">Wallet Paper Outcomes</h2>
            <div className="wallet-detail-list">
              {tradeRows.length ? tradeRows.slice(0, 8).map((trade, index) => <TradeRow trade={trade} key={`${trade.mint}-${trade.source}-${index}`} />) : <p className="muted">No paper trades directly attributed to this wallet.</p>}
            </div>
          </>
        ) : <p className="muted">Waiting for wallet performance data.</p>}
      </div>

      <div className="panel wallet-side">
        <WalletReviewApplyPanel payload={walletApply} onApplied={onWalletApply} />
        <div className="candidate-wallet-head">
          <div>
            <h2>Promotion Queue</h2>
            <p>{walletLifecycle?.summary?.promotion_review ?? 0} promote | {walletLifecycle?.summary?.demote_review ?? 0} demote</p>
          </div>
          <span>{walletLifecycle?.count ?? 0}</span>
        </div>
        <div className="candidate-wallet-list">
          {lifecycleRows.length ? lifecycleRows.slice(0, 8).map((row) => <LifecycleRow row={row} key={`${row.wallet}-${row.source}`} />) : <p className="muted">No wallet lifecycle report loaded.</p>}
        </div>
        <div className="candidate-wallet-head">
          <div>
            <h2>Candidate Wallet Review</h2>
            <p>{candidateWallets?.mode || "WATCH_ONLY_REVIEW"} | {candidateWallets?.summary?.untracked_wallets ?? 0} untracked | {candidateWallets?.review_summary?.paper_watch ?? 0} paper-watch</p>
          </div>
          <span>{candidateWallets?.count ?? 0}</span>
        </div>
        <div className="candidate-wallet-list">
          {candidateRows.length ? candidateRows.slice(0, 8).map((candidate) => <CandidateWalletRow candidate={candidate} key={candidate.wallet} />) : <p className="muted">No candidate wallet discovery file loaded yet.</p>}
        </div>
        <h2>{detail ? "Selected Wallet Signals" : "Recent Wallet Signals"}</h2>
        {signalRows.slice(0, 12).map((signal, index) => <SignalRow signal={signal} key={`${signal.mint}-${signal.time}-${index}`} />)}
        {signalRows.length ? null : <p className="muted">No recent wallet signals.</p>}
      </div>
    </section>
  );
}

function WalletReviewApplyPanel({ payload, onApplied }: { payload: WalletReviewApplyPayload | null; onApplied: (payload: WalletReviewApplyPayload) => void }) {
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const summary = payload?.summary || {};
  const hasApprovedChanges = Boolean((summary.promoted || 0) + (summary.demoted || 0));

  async function applyApprovedChanges() {
    setApplying(true);
    setApplyError(null);
    try {
      const result = await applyWalletReviewChanges();
      onApplied(result);
    } catch (error) {
      setApplyError(error instanceof Error ? error.message : "Wallet review apply failed.");
    } finally {
      setApplying(false);
    }
  }

  return (
    <div className="wallet-apply-panel">
      <div className="candidate-wallet-head">
        <div>
          <h2>Approved List Update</h2>
          <p>{payload?.dry_run === false ? "APPLIED" : "DRY RUN"} | local wallet metadata only</p>
        </div>
        <span>{summary.approved_decisions ?? 0}</span>
      </div>
      <div className="wallet-apply-summary">
        <Metric label="Promote" value={summary.promoted ?? 0} />
        <Metric label="Demote" value={summary.demoted ?? 0} />
        <Metric label="Skipped" value={summary.skipped ?? 0} />
      </div>
      {(payload?.changes || []).slice(0, 4).map((change) => (
        <div className="wallet-apply-change" key={`${change.wallet}-${change.action}`}>
          <strong>{applyActionLabel(change.action)}</strong>
          <small>{shortMint(change.wallet)} | {change.lifecycle_action || "approved decision"}</small>
        </div>
      ))}
      {payload?.changes?.length ? null : <p className="muted">No approved wallet list changes are ready to apply.</p>}
      {payload?.backup_dir ? <small className="decision-status">Backup: {payload.backup_dir}</small> : null}
      {applyError ? <small className="decision-status error">Apply failed: {applyError}</small> : null}
      <button
        type="button"
        className="wallet-apply-button"
        disabled={!hasApprovedChanges || applying}
        onClick={applyApprovedChanges}
      >
        {applying ? "Applying..." : "Apply Approved Wallet Changes"}
      </button>
      <small className="wallet-apply-note">Creates backups and audit records. Does not buy, sell, or unlock live execution.</small>
    </div>
  );
}

function LifecycleRow({ row }: { row: WalletLifecycleRow }) {
  const [savingDecision, setSavingDecision] = useState<WalletReviewDecisionRequest["decision"] | null>(null);
  const [savedDecision, setSavedDecision] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const lifecycle = row.lifecycle || {};
  const metrics = lifecycle.metrics || { entries: 0, wins: 0, losses: 0, score: 0, avg_pnl: 0, total_pnl: 0, win_rate: 0 };
  const rolling7d = lifecycle.rolling?.["7d"];
  const rolling30d = lifecycle.rolling?.["30d"];
  const postmortem = lifecycle.postmortem || {};
  const note = lifecycle.reasons?.[0] || lifecycle.blockers?.[0] || "review wallet performance";
  const actionClass = lifecycle.action === "DEMOTE_OFF_WATCH_REVIEW" ? "demote" : lifecycle.action === "PROMOTE_TO_TRUSTED_REVIEW" ? "promote" : "";
  const showPromote = lifecycle.action === "PROMOTE_TO_TRUSTED_REVIEW";
  const showDemote = lifecycle.action === "DEMOTE_OFF_WATCH_REVIEW";

  async function saveDecision(decision: WalletReviewDecisionRequest["decision"], approved: boolean, decisionNote: string) {
    setSavingDecision(decision);
    setDecisionError(null);
    try {
      await saveWalletReviewDecision({
        wallet: row.wallet,
        decision,
        approved,
        note: decisionNote,
      });
      setSavedDecision(decisionLabel(decision));
    } catch (error) {
      setDecisionError(error instanceof Error ? error.message : "Decision could not be saved.");
    } finally {
      setSavingDecision(null);
    }
  }

  return (
    <div className={`lifecycle-row ${actionClass}`}>
      <div className="lifecycle-title">
        <strong>{actionLabel(lifecycle.action)}</strong>
        <small>{shortMint(row.wallet)} | {row.source}</small>
      </div>
      <div className="lifecycle-stats">
        <Metric label="Trades" value={`${metrics.entries} (${metrics.wins}-${metrics.losses})`} />
        <Metric label="Win Rate" value={pct((metrics.win_rate || 0) * 100)} />
        <Metric label="Total PnL" value={money(metrics.total_pnl)} tone={tone(metrics.total_pnl)} />
        <Metric label="Avg PnL" value={money(metrics.avg_pnl)} tone={tone(metrics.avg_pnl)} />
        <Metric label="Score" value={score(metrics.score)} />
      </div>
      {(lifecycle.labels || []).length ? (
        <div className="wallet-label-row">
          {(lifecycle.labels || []).slice(0, 4).map((label) => <span key={label}>{label}</span>)}
        </div>
      ) : null}
      <div className="wallet-rolling-row">
        <small>7d {rollingSummary(rolling7d)}</small>
        <small>30d {rollingSummary(rolling30d)}</small>
      </div>
      <div className="wallet-postmortem-mini">
        <small>closed {postmortem.closed_trades ?? 0}</small>
        <small>failed {postmortem.failed_trades ?? 0}</small>
        <small>best {pct(postmortem.best_trade?.pnl_pct)}</small>
        <small>worst {pct(postmortem.worst_trade?.pnl_pct)}</small>
      </div>
      <p>{note}</p>
      <div className="lifecycle-actions" aria-label={`Review controls for ${shortMint(row.wallet)}`}>
        {showPromote ? (
          <button
            type="button"
            disabled={savingDecision !== null}
            onClick={() => saveDecision("approve_promotion", true, "Operator approved promotion from native Wallets review queue.")}
          >
            {savingDecision === "approve_promotion" ? "Saving..." : "Approve Promote"}
          </button>
        ) : null}
        {showDemote ? (
          <button
            type="button"
            className="danger"
            disabled={savingDecision !== null}
            onClick={() => saveDecision("approve_demotion", true, "Operator approved demotion from native Wallets review queue.")}
          >
            {savingDecision === "approve_demotion" ? "Saving..." : "Approve Demote"}
          </button>
        ) : null}
        <button
          type="button"
          className="quiet"
          disabled={savingDecision !== null}
          onClick={() => saveDecision("hold", false, "Operator chose to keep watching before changing wallet status.")}
        >
          {savingDecision === "hold" ? "Saving..." : "Hold"}
        </button>
        <button
          type="button"
          className="quiet"
          disabled={savingDecision !== null}
          onClick={() => saveDecision("reject", false, "Operator rejected this wallet lifecycle recommendation.")}
        >
          {savingDecision === "reject" ? "Saving..." : "Reject"}
        </button>
      </div>
      {savedDecision ? <small className="decision-status">Saved: {savedDecision}. Apply step still required.</small> : null}
      {decisionError ? <small className="decision-status error">Save failed: {decisionError}</small> : null}
    </div>
  );
}

function WalletBehaviorSummary({ detail }: { detail: WalletDetailPayload | null }) {
  const labels = detail?.behavior?.labels || [];
  const rolling = detail?.behavior?.rolling || {};
  if (!labels.length && !rolling["7d"] && !rolling["30d"]) return null;
  return (
    <div className="wallet-behavior-panel">
      {labels.length ? (
        <div className="wallet-label-row">
          {labels.map((label) => <span key={label}>{label}</span>)}
        </div>
      ) : null}
      <div className="wallet-rolling-row">
        <small>7d {rollingSummary(rolling["7d"])}</small>
        <small>30d {rollingSummary(rolling["30d"])}</small>
      </div>
    </div>
  );
}

function WalletPostmortemPanel({ postmortem }: { postmortem: WalletDetailPayload["postmortem"] | undefined }) {
  if (!postmortem || (!postmortem.closed_trades && !postmortem.failed_trades)) return null;
  const best = postmortem.best_trade;
  const worst = postmortem.worst_trade;
  return (
    <div className="wallet-postmortem-panel">
      <div className="wallet-postmortem-head">
        <div>
          <span>POSTMORTEM</span>
          <strong>{postmortem.closed_trades ?? 0} closed | {postmortem.failed_trades ?? 0} failed</strong>
        </div>
        <small>avg hold {duration(postmortem.avg_hold_seconds)}</small>
      </div>
      <div className="wallet-postmortem-grid">
        <OutcomeStat label="Best" trade={best} />
        <OutcomeStat label="Worst" trade={worst} />
      </div>
      <div className="wallet-reason-row">
        <small>Exit: {topReason(postmortem.exit_reasons)}</small>
        <small>Fail: {topReason(postmortem.failure_reasons)}</small>
      </div>
    </div>
  );
}

function OutcomeStat({ label, trade }: { label: string; trade?: WalletPostmortemTrade | null }) {
  const row = trade;
  return (
    <div>
      <span>{label}</span>
      <strong className={tone(row?.pnl_pct ?? undefined)}>{pct(row?.pnl_pct)}</strong>
      <small>{row?.mint ? shortMint(row.mint) : "-"} | {row?.reason || "no reason"}</small>
    </div>
  );
}

function CandidateWalletRow({ candidate }: { candidate: CandidateWallet }) {
  const status = candidate.already_tracked ? "TRACKED" : "NEW";
  const action = candidate.review?.action || candidate.recommended_tier || "HOLD_REVIEW";
  const reason = candidate.review?.reasons?.[0] || candidate.review?.blockers?.[0] || candidate.reasons?.[0] || "review evidence";
  return (
    <div className={candidate.already_tracked ? "candidate-wallet-row tracked" : "candidate-wallet-row"}>
      <div>
        <strong>{shortMint(candidate.wallet)}</strong>
        <small>{action} | {reason}</small>
      </div>
      <span>{score(candidate.score)}</span>
      <span>{status}</span>
      <div className="candidate-wallet-meta">
        <small>early {candidate.early_buy_events ?? 0}</small>
        <small>winners {candidate.winner_mints ?? 0}</small>
        <small>buys {candidate.buy_events ?? 0}</small>
        <small>mints {candidate.unique_mints ?? 0}</small>
      </div>
    </div>
  );
}

function WalletListRow({ wallet, active, onSelect }: { wallet: WalletRow; active: boolean; onSelect: (wallet: string) => void }) {
  return (
    <button className={active ? "wallet-row active" : "wallet-row"} onClick={() => onSelect(wallet.wallet)}>
      <div>
        <strong>{wallet.emoji ? `${wallet.emoji} ` : ""}{wallet.name || shortMint(wallet.wallet)}</strong>
        <small>{shortMint(wallet.wallet)}</small>
      </div>
      <span>{score(wallet.score)}</span>
      <span>{wallet.signals ?? 0}</span>
    </button>
  );
}

function SignalRow({ signal }: { signal: WalletSignal }) {
  return (
    <div className="wallet-signal-row">
      <strong>{signal.signal_type || "signal"}</strong>
      <small>{shortMint(signal.mint)} | score {score(signal.score)} | wallets {(signal.wallets || []).length}</small>
      <span>{signal.should_trade ? "TRADE" : "SKIP"}</span>
    </div>
  );
}

function TradeRow({ trade }: { trade: WalletTradeSummary }) {
  return (
    <div className="wallet-trade-row">
      <div>
        <strong>{trade.symbol || shortMint(trade.mint)}</strong>
        <small>{trade.status || trade.source || "paper"} | {trade.reason || "No reason recorded"}</small>
      </div>
      <span className={tone(trade.pnl_pct ?? undefined)}>{pct(trade.pnl_pct)}</span>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: "bad" | "good" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

function score(value: number | undefined): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) : "-";
}

function age(seconds: number | null | undefined): string {
  const number = Number(seconds);
  if (!Number.isFinite(number)) return "-";
  if (number < 60) return `${Math.round(number)}s`;
  if (number < 3600) return `${Math.round(number / 60)}m`;
  if (number < 86400) return `${Math.round(number / 3600)}h`;
  return `${Math.round(number / 86400)}d`;
}

function rollingSummary(window: { entries?: number; avg_pnl?: number; win_rate?: number } | undefined): string {
  if (!window || !window.entries) return "0 trades";
  return `${window.entries} trades | ${pct((window.win_rate || 0) * 100)} win | ${money(window.avg_pnl)} avg`;
}

function duration(seconds: number | null | undefined): string {
  const number = Number(seconds);
  if (!Number.isFinite(number) || number <= 0) return "-";
  if (number < 60) return `${Math.round(number)}s`;
  if (number < 3600) return `${Math.round(number / 60)}m`;
  return `${Math.round(number / 3600)}h`;
}

function topReason(reasons: Record<string, number> | undefined): string {
  const entries = Object.entries(reasons || {}).sort((a, b) => b[1] - a[1]);
  return entries.length ? `${entries[0][0]} (${entries[0][1]})` : "-";
}

function tone(value: number | undefined): "good" | "bad" | undefined {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return undefined;
  return number > 0 ? "good" : "bad";
}

function actionLabel(action: string | undefined): string {
  if (action === "PROMOTE_TO_TRUSTED_REVIEW") return "Promote Review";
  if (action === "DEMOTE_OFF_WATCH_REVIEW") return "Demote Review";
  if (action === "KEEP_TRUSTED") return "Keep Trusted";
  if (action === "KEEP_PAPER_WATCH") return "Keep Paper Watch";
  return action || "Observe";
}

function decisionLabel(decision: WalletReviewDecisionRequest["decision"]): string {
  if (decision === "approve_promotion") return "approved promotion";
  if (decision === "approve_demotion") return "approved demotion";
  if (decision === "hold") return "hold";
  return "rejected";
}

function applyActionLabel(action: string | undefined): string {
  if (action === "promoted_to_tracked") return "Promote to tracked";
  if (action === "demoted_from_tracked") return "Demote from tracked";
  return action || "Wallet update";
}
