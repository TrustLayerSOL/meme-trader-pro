import type { TradeRecord } from "../lib/api";
import { money, pct, price, shortMint } from "../lib/format";
import { tradeMint, tradeReason } from "../lib/trades";

type Props = {
  trade: TradeRecord | null;
};

export function TradeLifecycle({ trade }: Props) {
  if (!trade) {
    return (
      <div className="panel lifecycle-panel">
        <h2>Paper Trade Lifecycle</h2>
        <p className="muted">No paper trade record matched to the selected token.</p>
      </div>
    );
  }

  return (
    <div className="panel lifecycle-panel">
      <h2>Paper Trade Lifecycle</h2>
      <div className="lifecycle-head">
        <div>
          <strong>{trade.symbol || trade.name || shortMint(tradeMint(trade))}</strong>
          <small>{shortMint(tradeMint(trade))}</small>
        </div>
        <span className={trade.status === "open" ? "pill good-pill" : "pill"}>{trade.status || "recorded"}</span>
      </div>
      <div className="lifecycle-grid">
        <Metric label="Entry" value={price(trade.entry_price ?? trade.quoted_entry_price)} />
        <Metric label="Current" value={price(trade.current_price)} />
        <Metric label="Size" value={money(trade.size_usd ?? trade.entry_value)} />
        <Metric label="Value" value={money(trade.current_value)} />
        <Metric label="PNL" value={pct(trade.total_pnl_pct ?? trade.pnl_pct)} tone={Number(trade.total_pnl_pct ?? trade.pnl_pct) >= 0 ? "good" : "bad"} />
        <Metric label="Remaining" value={pct(trade.remaining_pct)} />
      </div>
      <div className="lifecycle-reason">
        <strong>Reason</strong>
        <span>{tradeReason(trade)}</span>
      </div>
      {trade.exit_advice ? (
        <div className="exit-advice">
          <strong>{trade.exit_advice.action || "WATCH"} | {trade.exit_advice.severity || "INFO"}</strong>
          <span>{(trade.exit_advice.reasons || []).join("; ") || "No advice reason recorded."}</span>
        </div>
      ) : null}
      <div className="wallet-strip">
        {(trade.wallets || []).slice(0, 4).map((wallet) => <span key={wallet}>{shortMint(wallet)}</span>)}
        {trade.wallets?.length ? null : <span>No source wallets recorded</span>}
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={tone || ""}>{value}</strong>
    </div>
  );
}
