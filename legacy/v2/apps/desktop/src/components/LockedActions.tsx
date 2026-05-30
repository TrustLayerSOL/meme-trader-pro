export function LockedActions() {
  return (
    <div className="panel actions-panel">
      <h2>Action Console</h2>
      <div className="action-stack">
        <span className="action-lock">Exit Now Locked</span>
        <span className="action-lock">Add Position Locked</span>
        <span className="action-lock">Protect Position Locked</span>
      </div>
      <div className="preset-row">
        <span className="action-lock">Sell 25% Locked</span>
        <span className="action-lock">Sell 50% Locked</span>
        <span className="action-lock">Sell 100% Locked</span>
      </div>
      <p className="locked-copy">Locked until live execution gates, quote checks, audit logging, and kill-switch behavior are explicitly armed.</p>
    </div>
  );
}
