import type { LogsPayload, OperatorConfigPayload } from "../lib/api";
import { EmptyState, LoadingState } from "./PanelState";

type Props = {
  config: OperatorConfigPayload | null;
  logs: LogsPayload | null;
};

export function OpsPanel({ config, logs }: Props) {
  const strategyEntries = Object.entries(config?.strategy || {});
  const components = config?.runtime?.components || [];
  const logEntries = Object.entries(logs?.logs || {});
  const providerRows = config?.providers?.providers || [];

  return (
    <section className="ops-grid">
      <div className="panel ops-main">
        <h2>Operator Config</h2>
        {!config ? <LoadingState title="Loading operator config" detail="Reading strategy, safety, provider, and refresh settings." rows={4} /> : (
          <>
            <div className="ops-lock-row">
              <Status label="Live Execution" value={config.live_execution_locked ? "LOCKED" : "UNLOCKED"} />
              <Status label="Mutations" value={config.safety?.mutations_enabled ? "ENABLED" : "OFF"} />
              <Status label="Auto Sell" value={config.safety?.auto_sell_enabled ? "ENABLED" : "OFF"} />
              <Status label="Paper First" value={config.safety?.paper_first ? "YES" : "NO"} />
            </div>
            <div className="ops-metric-grid">
              <Metric label="Selected Token Refresh" value={`${config.selected_token_refresh_ms ?? "-"}ms`} />
              <Metric label="Overview Refresh" value={`${config.overview_refresh_ms ?? "-"}ms`} />
              {strategyEntries.slice(0, 14).map(([key, value]) => <Metric label={key} value={formatValue(value)} key={key} />)}
            </div>
          </>
        )}
      </div>

      <div className="panel ops-runtime">
        <h2>Runtime Freshness</h2>
        {!config ? <LoadingState title="Loading runtime freshness" detail="Waiting for runtime heartbeat summary." rows={4} /> : components.map((component) => (
          <div className="ops-runtime-row" key={component.name}>
            <div>
              <strong>{component.name}</strong>
              <small>{component.detail || component.state || "-"}</small>
            </div>
            <span className={component.fresh ? "good-pill" : "bad-pill"}>{component.fresh ? "FRESH" : "STALE"}</span>
          </div>
        ))}
        {config && !components.length ? <EmptyState title="No runtime components" detail="No component heartbeat rows were returned by the desktop API." /> : null}
      </div>

      <div className="panel ops-providers">
        <h2>Provider Health</h2>
        {!config ? <LoadingState title="Loading provider health" detail="Checking Helius Gatekeeper, mainnet, and fallback status." rows={3} /> : (
          <>
            <div className="provider-summary">
              <Status label="RPC State" value={config.providers?.state || "NO DATA"} />
              <Status label="Active Provider" value={config.providers?.active_provider || "NONE"} />
            </div>
            {providerRows.map((provider) => (
              <div className="ops-runtime-row" key={provider.name}>
                <div>
                  <strong>{provider.name}</strong>
                  <small>{provider.detail || provider.error || provider.safe_url || "-"}</small>
                </div>
                <span className={provider.ok ? "good-pill" : "bad-pill"}>
                  {provider.ok ? "OK" : provider.http_status || provider.error || "FAIL"}
                </span>
              </div>
            ))}
            {!providerRows.length ? <EmptyState title="No provider rows" detail="Provider health did not return RPC endpoint results." /> : null}
          </>
        )}
      </div>

      <div className="panel ops-logs">
        <h2>Local Logs</h2>
        {!logs ? <LoadingState title="Loading local logs" detail="Reading redacted log tails from disk." rows={4} /> : logEntries.map(([name, log]) => (
          <div className="log-block" key={name}>
            <div className="log-title">
              <strong>{name}</strong>
              <span className={log.exists ? "good-pill" : "bad-pill"}>{log.exists ? "FOUND" : "MISSING"}</span>
            </div>
            <pre>{(log.lines || []).slice(-10).join("\n") || "No recent lines."}</pre>
          </div>
        ))}
        {logs && !logEntries.length ? <EmptyState title="No log payload" detail="The desktop API did not return log tail entries." /> : null}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label.replaceAll("_", " ")}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Status({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  if (typeof value === "boolean") return value ? "YES" : "NO";
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}
