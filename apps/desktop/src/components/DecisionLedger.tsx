import { useEffect, useMemo, useState } from "react";
import { loadDecisionExplanation, type DecisionExplanationPayload } from "../lib/api";
import {
  decisionMatchesFilter,
  decisionCatalystEvidenceSummary,
  decisionHolderClusterSummary,
  decisionMarketContextSummary,
  decisionPaperOutcomeSummary,
  decisionQuotePair,
  decisionQuoteReason,
  decisionRiskNotes,
  decisionRouteFeasibilitySummary,
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

export function DecisionLedger({ decisions, loaded, onSelectMint }: {
  decisions: DecisionLedgerPayload | null;
  loaded: boolean;
  onSelectMint: (mint: string) => void;
}) {
  const [filter, setFilter] = useState<DecisionFilter>("all");
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [explanation, setExplanation] = useState<DecisionExplanationPayload | null>(null);
  const [explanationLoading, setExplanationLoading] = useState(false);
  const [explanationError, setExplanationError] = useState("");
  const rows = decisions?.items || [];
  const filteredRows = useMemo(
    () => rows.filter((decision) => decisionMatchesFilter(decision, filter)),
    [rows, filter],
  );
  const selected = selectedDecisionForFilter(rows, selectedDecisionId, filter);

  useEffect(() => {
    setExplanation(null);
    setExplanationError("");
    setExplanationLoading(false);
  }, [selected?.decision_id]);

  function changeFilter(nextFilter: DecisionFilter) {
    setFilter(nextFilter);
    const nextSelected = selectedDecisionForFilter(rows, selectedDecisionId, nextFilter);
    setSelectedDecisionId(nextSelected?.decision_id || "");
  }

  async function explainSelectedDecision() {
    const decisionId = selected?.decision_id;
    if (!decisionId || explanationLoading) return;
    setExplanationLoading(true);
    setExplanationError("");
    try {
      setExplanation(await loadDecisionExplanation(decisionId));
    } catch (error) {
      setExplanation(null);
      setExplanationError(error instanceof Error ? error.message : String(error));
    } finally {
      setExplanationLoading(false);
    }
  }

  return (
    <div className="panel decision-ledger-panel">
      <div className="ledger-title">
        <div>
          <h2>Decision Ledger</h2>
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
          <DecisionDetail
            decision={selected}
            explanation={explanation}
            explanationLoading={explanationLoading}
            explanationError={explanationError}
            onExplain={explainSelectedDecision}
          />
          <div className="decision-table-head" aria-hidden="true">
            <span>Token / Lane</span>
            <span>Action</span>
            <span>Score</span>
            <span>Risk</span>
            <span>Quotes</span>
            <span>Reason</span>
          </div>
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
      <span><strong className={`decision-pill ${decisionActionTone(decision.final_action)}`}>{decision.final_action || "-"}</strong></span>
      <span><strong>{decision.total_score ?? "-"}</strong></span>
      <span><strong className={`decision-pill ${decisionRiskTone(decision.risk_label)}`}>{decision.risk_label || "-"}</strong></span>
      <span><strong>{decisionQuotePair(decision)}</strong></span>
      <span className="decision-reason"><strong>{decision.action_reason || "-"}</strong></span>
    </button>
  );
}

function DecisionDetail({
  decision,
  explanation,
  explanationLoading,
  explanationError,
  onExplain,
}: {
  decision: DecisionRecord | null;
  explanation: DecisionExplanationPayload | null;
  explanationLoading: boolean;
  explanationError: string;
  onExplain: () => void;
}) {
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
      <div className="decision-detail-head">
        <div>
          <h2>Decision Detail</h2>
          <strong>{shortMint(decision.mint || "")}</strong>
          <small>{decision.mint || "-"} | {decision.decision_id || "-"}</small>
        </div>
        <span className={`decision-pill ${decisionActionTone(decision.final_action)}`}>{decision.final_action || "-"}</span>
      </div>
      <div className="decision-detail-grid">
        <DecisionMetric label="Lane" value={decision.paper_lane || "-"} />
        <DecisionMetric label="Score" value={String(decision.total_score ?? "-")} />
        <DecisionMetric label="Threshold" value={String(decision.threshold ?? "-")} />
        <DecisionMetric label="Risk" value={decision.risk_label || "-"} />
        <DecisionMetric label="Buy Quote" value={decisionQuoteReason(decision, "buy")} />
        <DecisionMetric label="Sell Quote" value={decisionQuoteReason(decision, "sell")} />
      </div>
      <div className="decision-detail-notes">
        <DecisionNote label="Reason" value={decision.action_reason || "-"} />
        <DecisionAiNote
          explanation={explanation}
          loading={explanationLoading}
          error={explanationError}
          disabled={!decision.decision_id}
          onExplain={onExplain}
        />
        <DecisionNote label="Wallets" value={decisionWalletSummary(decision)} />
        <DecisionNote label="Social" value={decisionSocialSummary(decision)} />
        <DecisionNote label="Catalyst Evidence" value={decisionCatalystEvidenceSummary(decision)} />
        <DecisionNote label="Route Feasibility" value={decisionRouteFeasibilitySummary(decision)} />
        <DecisionNote label="Holder / Cluster" value={decisionHolderClusterSummary(decision)} />
        <DecisionNote label="Market Context" value={decisionMarketContextSummary(decision)} />
        <DecisionNote label="Paper Outcome" value={decisionPaperOutcomeSummary(decision)} />
        <DecisionNote label="Risk Notes" value={decisionRiskNotes(decision)} />
        <DecisionNote label="Score Notes" value={decisionScoreNotes(decision)} />
      </div>
    </div>
  );
}

function DecisionAiNote({
  explanation,
  loading,
  error,
  disabled,
  onExplain,
}: {
  explanation: DecisionExplanationPayload | null;
  loading: boolean;
  error: string;
  disabled: boolean;
  onExplain: () => void;
}) {
  const detail = explanation?.advisory || explanation?.detail || error || "Advisory only. Click to generate a plain-language decision review.";
  return (
    <div className="decision-ai-note">
      <div className="decision-ai-head">
        <strong>OpenAI Advisory</strong>
        <button type="button" onClick={onExplain} disabled={disabled || loading}>
          {loading ? "Explaining..." : "Explain Decision"}
        </button>
      </div>
      <p>{detail}</p>
      <small>
        Advisory only | {explanation?.available === false ? explanation.status || "unavailable" : "does not trade"}
      </small>
    </div>
  );
}

function decisionActionTone(action?: string | null): string {
  const normalized = String(action || "").toLowerCase();
  if (normalized.includes("buy") || normalized.includes("open")) return "good";
  if (normalized.includes("block") || normalized.includes("fail") || normalized.includes("hard")) return "bad";
  if (normalized.includes("skip")) return "warn";
  return "neutral";
}

function decisionRiskTone(risk?: string | null): string {
  const normalized = String(risk || "").toLowerCase();
  if (normalized.includes("danger") || normalized.includes("high") || normalized.includes("block")) return "bad";
  if (normalized.includes("warn") || normalized.includes("watch")) return "warn";
  if (normalized.includes("low") || normalized.includes("ok")) return "good";
  return "neutral";
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
