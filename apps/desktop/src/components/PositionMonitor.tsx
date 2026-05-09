import type { PositionDetailPayload, SnapshotPayload } from "../lib/api";
import { money, pct, price, shortMint } from "../lib/format";

type Position = {
  mint: string;
  label: string;
  source: string;
  status: string;
  price: number | null;
  liquidity: number | null;
  market_cap?: number | null;
  risk_level?: string | null;
  alert_level?: string | null;
  holder_count?: number | null;
  top_10_holder_pct?: number | null;
  quote_status?: string | null;
  pnl_pct?: number | null;
};

type Props = {
  position?: Position;
  detail: PositionDetailPayload | null;
  snapshots: SnapshotPayload | null;
};

export function PositionMonitor({ position, detail, snapshots }: Props) {
  const latest = detail?.latest_snapshot;
  const latestSnapshot = snapshots?.snapshots?.[snapshots.snapshots.length - 1];
  const market = latest?.market_info;
  const sourcePosition = detail?.position || position;

  return (
    <div className="panel monitor-panel">
      <h2>Position Monitor</h2>
      <div className="monitor-title">
        <div>
          <strong>{sourcePosition?.label || market?.symbol || shortMint(position?.mint)}</strong>
          <small>{shortMint(position?.mint || detail?.mint)} | {sourcePosition?.source || "local"}</small>
        </div>
        <span className="pill">{sourcePosition?.status || "UNKNOWN"}</span>
      </div>
      <div className="monitor-grid">
        <Metric label="Market Cap" value={money(sourcePosition?.market_cap ?? market?.market_cap)} />
        <Metric label="Liquidity" value={money(sourcePosition?.liquidity ?? market?.liquidity)} />
        <Metric label="Holders" value={sourcePosition?.holder_count ?? "-"} />
        <Metric label="Top 10" value={pct(sourcePosition?.top_10_holder_pct)} />
        <Metric label="PNL" value={pct(sourcePosition?.pnl_pct)} tone={Number(sourcePosition?.pnl_pct) >= 0 ? "good" : "bad"} />
        <Metric label="Quote" value={sourcePosition?.quote_status || latest?.sell_quote_reason || "-"} />
        <Metric label="Risk" value={sourcePosition?.risk_level || sourcePosition?.alert_level || latest?.risk_label || "-"} />
        <Metric label="Snapshot Age" value={formatAge(detail?.trend?.latest_age_seconds)} />
      </div>
      <div className="monitor-grid compact">
        <Metric label="Price" value={price(sourcePosition?.price ?? market?.price)} />
        <Metric label="24h Chg" value={pct(market?.price_change_24h)} />
        <Metric label="Wallets" value={latest?.wallet_count ?? "-"} />
        <Metric label="Score" value={scoreValue(latest?.total_score, latest?.score_threshold)} />
      </div>
      <div className="monitor-note">
        <strong>{detail?.trend?.latest_context || latestSnapshot?.context || "latest local snapshot"}</strong>
        <span>{detail?.trend?.latest_source || latestSnapshot?.source || market?.dex || "local state"} | {latest?.mode || "paper/read-only"}</span>
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string | number; tone?: "good" | "bad" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}

function formatAge(seconds: number | undefined): string {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "-";
  if (value < 60) return `${Math.max(0, Math.round(value))}s`;
  if (value < 3600) return `${Math.round(value / 60)}m`;
  return `${Math.round(value / 3600)}h`;
}

function scoreValue(score: number | undefined, threshold: number | undefined): string {
  if (!Number.isFinite(Number(score))) return "-";
  return Number.isFinite(Number(threshold)) ? `${Number(score).toFixed(1)} / ${Number(threshold).toFixed(1)}` : Number(score).toFixed(1);
}
