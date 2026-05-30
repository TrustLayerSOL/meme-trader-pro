type PanelStateProps = {
  title?: string;
  detail?: string;
  rows?: number;
};

export function LoadingState({ title = "Loading local state", detail = "Waiting for the desktop API payload.", rows = 3 }: PanelStateProps) {
  return (
    <div className="panel-state loading-state" aria-busy="true">
      <strong>{title}</strong>
      <span>{detail}</span>
      <div className="skeleton-stack">
        {Array.from({ length: rows }).map((_, index) => <i key={index} />)}
      </div>
    </div>
  );
}

export function EmptyState({ title = "No local data loaded", detail = "This panel will populate when the matching runtime source writes data." }: PanelStateProps) {
  return (
    <div className="panel-state empty-state">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}
