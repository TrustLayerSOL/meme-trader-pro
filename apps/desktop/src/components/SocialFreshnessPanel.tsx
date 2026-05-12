import type { SocialFreshnessPayload, SocialFreshnessRow } from "../lib/api";
import { EmptyState, LoadingState } from "./PanelState";

export function SocialFreshnessPanel({ freshness, loaded = true }: {
  freshness?: SocialFreshnessPayload | null;
  loaded?: boolean;
}) {
  const rows = freshness?.rows || [];
  return (
    <div className="panel social-freshness-panel">
      <div className="candidate-feed-head">
        <div>
          <h2>Social Freshness</h2>
          <p className="muted">Collector visibility only. Social data cannot trigger trades or bypass risk gates.</p>
        </div>
        <span className={statusTone(freshness?.overall)}>{loaded ? freshness?.overall || "NO DATA" : "LOADING"}</span>
      </div>
      {!loaded ? <LoadingState title="Loading social freshness" detail="Checking manual imports, catalyst cards, and collector status." rows={3} /> : null}
      {loaded && !rows.length ? <EmptyState title="No social freshness rows" detail="Collector freshness rows were not present in the desktop API payload." /> : null}
      {rows.map((row) => <SocialFreshnessRowView key={row.source} row={row} />)}
    </div>
  );
}

function SocialFreshnessRowView({ row }: { row: SocialFreshnessRow }) {
  return (
    <div className="source-row social-source-row">
      <div>
        <strong>{row.label || row.source}</strong>
        <small>{row.collector_type || "source"} | {row.event_count ?? 0} events | {row.detail || "-"}</small>
      </div>
      <span className={statusTone(row.status)}>{row.status}</span>
      <small>{row.age || "N/A"}</small>
    </div>
  );
}

function statusTone(status?: string): string {
  const normalized = String(status || "").toUpperCase();
  if (["OK", "FRESH", "DISABLED"].includes(normalized)) return "good-pill";
  if (["ERROR", "FAIL", "OLD"].includes(normalized)) return "bad-pill";
  return "warn-pill";
}
