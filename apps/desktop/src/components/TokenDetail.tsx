import type { PositionDetailPayload } from "../lib/api";
import { money, pct, shortMint } from "../lib/format";
import { EmptyState, LoadingState } from "./PanelState";

type Props = {
  detail: PositionDetailPayload | null;
  loading?: boolean;
};

export function TokenDetail({ detail, loading = false }: Props) {
  if (loading) {
    return (
      <section className="token-detail-grid">
        <div className="panel token-detail-state">
          <LoadingState title="Loading selected-token detail" detail="Reading mechanics, holder risk, quote feasibility, and source contracts." rows={5} />
        </div>
      </section>
    );
  }
  if (!detail) {
    return (
      <section className="token-detail-grid">
        <div className="panel token-detail-state">
          <EmptyState title="No token detail selected" detail="Select a paper position, protected token, wallet event, or scanner candidate to inspect the full diagnostic record." />
        </div>
      </section>
    );
  }
  const latest = detail?.latest_snapshot;
  const protection = detail?.protection;
  const mechanicsRisk = protection?.token_mechanics_risk || latest?.token_mechanics_risk || latest?.risk_label || "UNKNOWN";
  const holderRisk = latest?.holder_concentration_risk || "UNKNOWN";

  return (
    <section className="token-detail-grid">
      <div className="panel token-card">
        <h2>Token Mechanics</h2>
        <div className="rail-status neutral">
          <span>{protection?.token_standard || latest?.token_standard || "UNKNOWN"}</span>
          <strong>{mechanicsRisk}</strong>
        </div>
        <KeyValue label="Extensions" value={listValue(protection?.token_extensions || latest?.token_extensions)} />
        <KeyValue label="Hard Block" value={latest?.hard_block ? "YES" : "NO"} tone={latest?.hard_block ? "bad" : "good"} />
        <KeyValue label="Reason" value={latest?.hard_block_reason || "No hard block recorded"} />
        <ReasonList items={protection?.reasons || latest?.token_mechanics_reasons || []} empty="No token mechanics reasons recorded." />
      </div>

      <div className="panel token-card">
        <h2>Holder / Dev Risk</h2>
        <div className="mini-grid">
          <div><span>Holder Risk</span><strong>{holderRisk}</strong></div>
          <div><span>Holders</span><strong>{latest?.holder_count ?? detail?.position?.holder_count ?? "-"}</strong></div>
          <div><span>Top 1</span><strong>{pct(latest?.holder_top_1_pct)}</strong></div>
          <div><span>Top 5</span><strong>{pct(latest?.holder_top_5_pct)}</strong></div>
          <div><span>Top 10</span><strong>{pct(latest?.holder_top_10_pct ?? detail?.position?.top_10_holder_pct)}</strong></div>
          <div><span>Bonded Dev</span><strong>{latest?.dev_bonded_tokens ?? 0}</strong></div>
        </div>
        <KeyValue label="Dev Label" value={latest?.dev_label || "UNKNOWN_DEV"} />
        <KeyValue label="Dev Wallet" value={shortMint(latest?.dev_wallet)} />
      </div>

      <div className="panel token-card">
        <h2>Quote Feasibility</h2>
        <div className="quote-grid">
          <QuoteBox label="Buy Quote" pass={latest?.buy_quote_pass} reason={latest?.buy_quote_reason} impact={latest?.buy_quote_price_impact_pct} />
          <QuoteBox label="Sell Quote" pass={latest?.sell_quote_pass} reason={latest?.sell_quote_reason || protection?.quote_status} impact={latest?.sell_quote_price_impact_pct} />
        </div>
        <KeyValue label="Prepared Exit" value={protection?.suggested_sell_pct ? `${protection.suggested_sell_pct}% ${protection.urgency || ""}` : "No prepared exit"} />
        <KeyValue label="Live Action" value={protection?.live_action_allowed || detail?.position?.live_action_allowed ? "ALLOWED" : "LOCKED"} tone="bad" />
      </div>

      <WalletConfidenceCard detail={detail} />

      <div className="panel token-card">
        <h2>Data Sources</h2>
        <KeyValue label="Position" value={sourceLabel(detail?.position_source, detail?.position_source_detail)} />
        <KeyValue label="Snapshots" value={sourceLabel(detail?.snapshot_source, detail?.snapshot_source_detail)} />
        <KeyValue label="Social" value={detail?.source_contract?.social || "unknown"} />
        <KeyValue label="Wallet Context" value={detail?.source_contract?.wallet_context || detail?.source_contract?.wallet_stats || "unknown"} />
        <KeyValue label="Mixed Fields" value={detail?.mixed_market_fields ? "YES" : "NO"} tone={detail?.mixed_market_fields ? "bad" : undefined} />
        <p className="muted">{detail?.mixed_market_fields_note || "Selected-token fields use one declared source contract."}</p>
      </div>

      <div className="panel token-card wide-token-card">
        <h2>Decision Record</h2>
        <div className="decision-strip">
          <span>Risk: <strong>{latest?.risk_label || protection?.risk_level || "UNKNOWN"}</strong></span>
          <span>Score: <strong>{scoreValue(latest?.total_score, latest?.score_threshold)}</strong></span>
          <span>Mode: <strong>{latest?.mode || "paper/read-only"}</strong></span>
          <span>Should Trade: <strong>{latest?.should_trade ? "YES" : "NO"}</strong></span>
          <span>Confirmation: <strong>{latest?.confirmation_allow ? "ALLOW" : "BLOCK"}</strong></span>
        </div>
        <ReasonList title="Risk Warnings" items={latest?.risk_warnings || []} empty="No risk warnings recorded." />
        <ReasonList title="Confirmation / Score Reasons" items={[...(latest?.confirmation_reasons || []), ...(latest?.score_reasons || [])].slice(0, 10)} empty="No confirmation reasons recorded." />
        <KeyValue label="Strategy Guard" value={`${latest?.strategy_guard_action || "-"} | ${latest?.strategy_guard_reason || "no guard reason"}`} />
      </div>
    </section>
  );
}

function WalletConfidenceCard({ detail }: { detail: PositionDetailPayload | null }) {
  const context = detail?.wallet_context;
  const wallets = context?.wallets || [];
  return (
    <div className="panel token-card wallet-confidence-card">
      <h2>Wallet Confidence</h2>
      <div className="mini-grid">
        <div><span>Wallets</span><strong>{context?.wallet_count ?? 0}</strong></div>
        <div><span>Signals</span><strong>{context?.matched_signals ?? 0}</strong></div>
        <div><span>Proven</span><strong className={(context?.proven_wallets || 0) ? "good" : ""}>{context?.proven_wallets ?? 0}</strong></div>
        <div><span>Traps</span><strong className={(context?.trap_wallets || 0) ? "bad" : ""}>{context?.trap_wallets ?? 0}</strong></div>
        <div><span>Avg Score</span><strong>{scoreValue(context?.avg_score, undefined)}</strong></div>
        <div><span>Live</span><strong className="bad">{context?.live_execution_locked === false ? "UNLOCKED" : "LOCKED"}</strong></div>
      </div>
      <div className="token-wallet-list">
        {wallets.slice(0, 4).map((wallet) => (
          <div className="token-wallet-row" key={wallet.wallet}>
            <div>
              <strong>{wallet.name || shortMint(wallet.wallet)}</strong>
              <small>{shortMint(wallet.wallet)} | {wallet.matched_signal_count ?? 0} matched signals</small>
            </div>
            <span>{scoreValue(wallet.score, undefined)}</span>
            <span className={Number(wallet.avg_pnl) > 0 ? "good" : Number(wallet.avg_pnl) < 0 ? "bad" : ""}>{money(wallet.avg_pnl)}</span>
            <small>{wallet.postmortem?.closed_trades ?? 0} closed / {wallet.postmortem?.failed_trades ?? 0} failed</small>
            {(wallet.labels || []).length ? (
              <div className="token-wallet-labels">
                {(wallet.labels || []).slice(0, 3).map((label) => <em key={label}>{label}</em>)}
              </div>
            ) : null}
          </div>
        ))}
        {wallets.length ? null : <p className="muted">No wallet context matched this selected token yet.</p>}
      </div>
    </div>
  );
}

function QuoteBox({ label, pass, reason, impact }: { label: string; pass?: boolean; reason?: string | null; impact?: number | null }) {
  const known = typeof pass === "boolean";
  return (
    <div className="quote-box">
      <span>{label}</span>
      <strong className={known ? (pass ? "good" : "bad") : ""}>{known ? (pass ? "PASS" : "FAIL") : "UNKNOWN"}</strong>
      <small>{reason || "no quote reason"}</small>
      <small>impact {pct(impact)}</small>
    </div>
  );
}

function KeyValue({ label, value, tone }: { label: string; value: string | number; tone?: "good" | "bad" }) {
  return (
    <div className="key-value">
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

function ReasonList({ title, items, empty }: { title?: string; items: string[]; empty: string }) {
  return (
    <div className="reason-list">
      {title ? <strong>{title}</strong> : null}
      {items.length ? items.slice(0, 8).map((item) => <p key={item}>{item}</p>) : <p>{empty}</p>}
    </div>
  );
}

function listValue(items: string[] | undefined): string {
  return items?.length ? items.join(", ") : "none recorded";
}

function sourceLabel(source?: string | null, detail?: string | null): string {
  if (!source) return "unknown";
  return detail ? `${source} | ${detail}` : source;
}

function scoreValue(score: number | undefined, threshold: number | undefined): string {
  if (!Number.isFinite(Number(score))) return "-";
  return Number.isFinite(Number(threshold)) ? `${Number(score).toFixed(1)} / ${Number(threshold).toFixed(1)}` : Number(score).toFixed(1);
}
