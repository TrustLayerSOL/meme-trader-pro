export async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function desktopApiToken() {
  try {
    return new URLSearchParams(window.location.search).get("api_token") || window.__MTP_API_TOKEN || "";
  } catch {
    return window.__MTP_API_TOKEN || "";
  }
}

export async function postJson(url, payload) {
  const headers = { "Content-Type": "application/json" };
  const token = desktopApiToken();
  if (token) headers["X-MemeTraderPro-Token"] = token;
  const response = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const errorPayload = await response.json();
      detail = errorPayload.error || detail;
    } catch {
      // Keep HTTP status fallback.
    }
    throw new Error(detail);
  }
  return response.json();
}

export async function loadCoreState() {
  const [overview, positionsPayload] = await Promise.all([
    getJson("/api/overview"),
    getJson("/api/positions"),
  ]);
  const [trades, watchlist, social, catalysts, readiness, winnerPatterns, decisions, paperReview, decisionAnalytics, marketRadarReview] = await Promise.all([
    getJson("/api/trades"),
    getJson("/api/watchlist"),
    getJson("/api/social"),
    getJson("/api/catalyst-cards"),
    getJson("/api/readiness"),
    getJson("/api/winner-patterns"),
    getJson("/api/decisions?limit=80"),
    getJson("/api/paper-review"),
    getJson("/api/decision-analytics?limit=5000"),
    getJson("/api/market-radar-review?limit=120"),
  ]);
  return {
    overview,
    positions: positionsPayload.positions || [],
    trades,
    watchlist,
    social,
    catalysts,
    readiness,
    winnerPatterns,
    decisions,
    paperReview,
    decisionAnalytics,
    marketRadarReview,
  };
}

export function saveProtectedToken(payload) {
  return postJson("/api/watchlist/protected-token", payload);
}

export function importSocialSignal(payload) {
  return postJson("/api/social/import", payload);
}

export function loadDecisionExplanation(decisionId) {
  return getJson(`/api/decisions/${encodeURIComponent(decisionId)}/explanation`);
}

export async function loadTokenState(mint, metric = "price", interval = 1, limit = 160) {
  if (!mint) {
    return {
      candles: { candles: [], snapshot_count: 0, metric, interval_seconds: interval },
      detail: { position: null, snapshot_count: 0 },
      snapshots: { snapshots: [] },
    };
  }
  const safeInterval = [1, 5, 30, 60].includes(Number(interval)) ? Number(interval) : 1;
  const safeLimit = Math.max(20, Math.min(500, Number(limit) || 500));
  const safeMetric = ["market_cap", "price", "liquidity"].includes(String(metric)) ? String(metric) : "market_cap";
  const [candles, detail, snapshots] = await Promise.all([
    getJson(`/api/candles?mint=${encodeURIComponent(mint)}&limit=${encodeURIComponent(String(safeLimit))}&metric=${encodeURIComponent(safeMetric)}&interval=${encodeURIComponent(String(safeInterval))}`),
    getJson(`/api/positions/${encodeURIComponent(mint)}`),
    getJson(`/api/tokens/${encodeURIComponent(mint)}/snapshots?limit=25`),
  ]);
  return { candles, detail, snapshots };
}
