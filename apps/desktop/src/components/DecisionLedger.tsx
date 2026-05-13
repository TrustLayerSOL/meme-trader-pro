import { useMemo, useState } from "react";
import {
  decisionMatchesFilter,
  decisionMarketSummary,
  decisionOutcomeSummary,
  decisionQuoteDetail,
  decisionQuotePair,
  decisionQuoteReason,
  decisionRiskDetail,
  decisionRiskNotes,
  decisionScoreNotes,
  decisionSocialSummary,
  decisionWalletSummary,
  selectedDecisionForFilter,
  type DecisionFilter,
  type DecisionLedgerPayload,
  type DecisionRecord,
} from "../lib/decisions";
import { shortMint } from "../lib/format";
import { EmptyState, LoadingState } from "./PanelState";

const FILTERS: Array<{ value: DecisionFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "bought", label: "Bought" },
  { value: "skipped", label: "Skipped" },
  { value: "exploration", label: "Exploration" },
  { value: "quote_failed", label: "Quote Failed" },
  { value: "hard_risk", label: "Hard Risk" },
  { value: "social", label: "Social" },
  { value: "wallet", label: "Wallet" },
];

/** Filterable canonical decision audit (replay tab primary surface). */
export function DecisionLedger({ decisions, loaded, onSelectMint }: {
  decisions: DecisionLedgerPayload | null;
  loaded: boolean;
  onSelectMint: (mint: string) => void;
}) {
  const [filter, setFilter] = useState<DecisionFilter>("all");
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const rows = decisions?.items || [];
  const filteredRows = useMemo(
    () => rows.filter((decision) => decisionMatchesFilter(decision, filter)),
    [rows, filter],
  );
  const selected = selectedDecisionForFilter(rows, selectedDecisionId, filter);

  /** Updates the active filter and re-syncs the highlighted decision row. */
  function changeFilter(nextFilter: DecisionFilter) {
    setFilter(nextFilter);
    const nextSelected = selectedDecisionForFilter(rows, selectedDecisionId, nextFilter);
    setSelectedDecisionId(nextSelected?.decision_id || "");
  }

  return (
    <div className="panel decision-ledger-panel">
      <div className="ledger-title">
        <div>
          <h2>Decision Ledger</h2>
          <p className="muted">Canonical log of buy, skip, and block verdicts with filterable slices.</p>
          <small>{decisions ? `${decisions.count ?? rows.length} recent records | canonical candidate audit trail` : "loading canonical decisions"}</small>
        </div>
        <span>{decisions?.live_execution_locked === false ? "UNLOCKED" : "LOCKED"}</span>
      </div>
      {!loaded ? <LoadingState title="Loading decision ledger" detail="Reading canonical candidate decisions." rows={4} /> : null}
      {loaded && !rows.length ? <EmptyState title="No decision records" detail="Replay falls back to paper trades until scanner decisions populate the canonical ledger." /> : null}
      {rows.length ? (
        <>
          <div className="decision-filter-row">
            {FILTERS.map((item) => (
              <button key={item.value} type="button" className={filter === item.value ? "active" : ""} onClick={() => changeFilter(item.value)}>
                {item.label}
              </button>
            ))}
          </div>
          <DecisionDetail decision={selected} />
          <div className="decision-row-list">
            {filteredRows.slice(0, 30).map((decision) => (
              <DecisionRow
                key={decision.decision_id || `${decision.mint}-${decision.created_at}`}
                decision={decision}
                selected={decision.decision_id === selected?.decision_id}
                onSelect={() => {
                  setSelectedDecisionId(decision.decision_id || "");
                  if (decision.mint) onSelectMint(decision.mint);
                }}
              />
            ))}
            {!filteredRows.length ? <div className="ledger-empty">No decisions match this filter.</div> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

function DecisionRow({ decision, selected, onSelect }: { decision: DecisionRecord; selected: boolean; onSelect: () => void }) {
  return (
    <button type="button" className={selected ? "decision-row active" : "decision-row"} onClick={onSelect}>
      <span>
        <strong>{shortMint(decision.mint || "")}</strong>
        <small>{decision.signal_type || "-"} | {decision.paper_lane || "-"}</small>
      </span>
      <span><small>Action</small><strong>{decision.final_action || "-"}</strong></span>
      <span><small>Score</small><strong>{decision.total_score ?? "-"}</strong></span>
      <span><small>Risk</small><strong>{decision.risk_label || "-"}</strong></span>
      <span><small>Quotes</small><strong>{decisionQuotePair(decision)}</strong></span>
      <span className="decision-reason"><small>Reason</small><strong>{decision.action_reason || "-"}</strong></span>
    </button>
  );
}

function DecisionDetail({ decision }: { decision: DecisionRecord | null }) {
  if (!decision) {
    return (
      <div className="decision-detail">
        <strong>Decision Detail</strong>
        <p>No decision selected.</p>
      </div>
    );
  }
  return (
    <div className="decision-detail">
      <div className="trade-detail-head">
        <div>
          <h2>Decision Detail</h2>
          <strong>{shortMint(decision.mint || "")}</strong>
          <small>{decision.mint || "-"} | {decision.decision_id || "-"}</small>
        </div>
        <span>{decision.final_action || "-"}</span>
      </div>
      <div className="trade-detail-grid">
        <DecisionMetric label="Lane" value={decision.paper_lane || "-"} />
        <DecisionMetric label="Score" value={String(decision.total_score ?? "-")} />
        <DecisionMetric label="Threshold" value={String(decision.threshold ?? "-")} />
        <DecisionMetric label="Risk" value={decision.risk_label || "-"} />
        <DecisionMetric label="Buy Quote" value={decisionQuoteReason(decision, "buy")} />
        <DecisionMetric label="Sell Quote" value={decisionQuoteReason(decision, "sell")} />
        <DecisionMetric label="Market" value={decisionMarketSummary(decision)} />
        <DecisionMetric label="Outcome" value={decisionOutcomeSummary(decision)} />
      </div>
      <div className="trade-detail-notes">
        <DecisionNote label="Reason" value={decision.action_reason || "-"} />
        <DecisionNote label="Quote Detail" value={`Buy: ${decisionQuoteDetail(decision, "buy")} | Sell: ${decisionQuoteDetail(decision, "sell")}`} />
        <DecisionNote label="Wallets" value={decisionWalletSummary(decision)} />
        <DecisionNote label="Social" value={decisionSocialSummary(decision)} />
        <DecisionNote label="Risk Detail" value={decisionRiskDetail(decision)} />
        <DecisionNote label="Risk Notes" value={decisionRiskNotes(decision)} />
        <DecisionNote label="Score Notes" value={decisionScoreNotes(decision)} />
      </div>
    </div>
  );
}

function DecisionMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DecisionNote({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <strong>{label}</strong>
      <p>{value}</p>
    </div>
  );
}
