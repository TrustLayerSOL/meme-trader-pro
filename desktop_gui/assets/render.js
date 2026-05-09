import { $, escapeHtml, money, pct, price, shortMint } from "./format.js";

export function renderOverview(state) {
  const overview = state.overview;
  if (!overview) return;
  const runtime = overview.runtime || {};
  const pill = $("runtime-pill");
  pill.textContent = runtime.state === "online" ? "CONNECTED" : "STALE";
  pill.className = `status-pill ${runtime.state === "online" ? "online" : "stale"}`;

  $("runtime-list").innerHTML = (runtime.components || []).map((item) => `
    <div class="runtime-row">
      <span><i class="dot ${item.fresh ? "fresh" : ""}"></i> ${escapeHtml(item.name)}</span>
      <small>${escapeHtml(item.state || "unknown")}</small>
    </div>
  `).join("");

  const counts = overview.counts || {};
  $("overview-counts").innerHTML = [
    ["Open", counts.open_trades],
    ["Protected", counts.protected_positions],
    ["Social", counts.social_events],
    ["Catalysts", counts.catalyst_cards],
  ].map(([label, value]) => `
    <div class="stat-row"><span>${label}</span><strong>${value ?? 0}</strong></div>
  `).join("");
}

export function renderPositions(state, onSelect) {
  const list = $("position-list");
  if (!state.positions.length) {
    list.innerHTML = `<div class="position-row"><span>No active positions</span><small>paper/watchlist empty</small></div>`;
    return;
  }
  if (!state.selectedMint) state.selectedMint = state.positions[0].mint;
  list.innerHTML = state.positions.map((position) => `
    <div class="position-row ${position.mint === state.selectedMint ? "active" : ""}" data-mint="${escapeHtml(position.mint)}">
      <span>${escapeHtml(position.label || shortMint(position.mint))}<br><small>${escapeHtml(shortMint(position.mint))}</small></span>
      <small>${escapeHtml(position.source || "-")}</small>
    </div>
  `).join("");
  list.querySelectorAll("[data-mint]").forEach((row) => {
    row.addEventListener("click", () => onSelect(row.dataset.mint));
  });
  renderSelectedPosition(state);
}

export function renderSelectedPosition(state) {
  const position = state.positions.find((item) => item.mint === state.selectedMint) || state.positions[0];
  if (!position) return;
  $("token-name").textContent = position.label || shortMint(position.mint);
  $("token-mint").textContent = `${position.mint} | ${position.source || "source"} | ${position.status || "status"}`;
  $("metric-mc").textContent = money(position.market_cap);
  $("metric-price").textContent = price(position.price);
  $("metric-liq").textContent = money(position.liquidity);
  $("metric-risk").textContent = position.risk_level || position.alert_level || "UNKNOWN";
}

export function renderTokenLoading() {
  $("chart").innerHTML = "";
  $("chart-empty").classList.remove("hidden");
  $("chart-empty").textContent = "Loading selected token...";
  $("snapshot-count").textContent = "loading";
  $("chart-range").textContent = "-";
  $("position-detail").innerHTML = `<div class="detail-row"><span>Selected Token</span><strong>Loading</strong></div>`;
  $("snapshot-feed").innerHTML = `<div class="snapshot-row"><strong>Loading</strong><small>Reading local token snapshots.</small></div>`;
  const protectionRail = $("protection-rail");
  if (protectionRail) {
    protectionRail.innerHTML = `<div class="protection-status warn"><span>Protection</span><strong>Loading</strong></div>`;
  }
  const signalRail = $("signal-rail");
  if (signalRail) {
    signalRail.innerHTML = `<div class="signal-card empty"><strong>Loading signals</strong><p>Reading local catalyst and social records.</p></div>`;
  }
}

export function renderTokenError(error) {
  const message = error && error.message ? error.message : "Unknown selected-token error";
  $("chart").innerHTML = "";
  $("chart-empty").classList.remove("hidden");
  $("chart-empty").textContent = `Selected token error: ${message}`;
  $("snapshot-count").textContent = "error";
  $("chart-range").textContent = "-";
  $("position-detail").innerHTML = `<div class="detail-row"><span>Error</span><strong>${escapeHtml(message)}</strong></div>`;
  $("snapshot-feed").innerHTML = `<div class="snapshot-row"><strong>Error</strong><small>${escapeHtml(message)}</small></div>`;
  const protectionRail = $("protection-rail");
  if (protectionRail) {
    protectionRail.innerHTML = `<div class="protection-status danger"><span>Protection</span><strong>Error</strong></div>`;
  }
  const signalRail = $("signal-rail");
  if (signalRail) {
    signalRail.innerHTML = `<div class="signal-card empty"><strong>Signal error</strong><p>${escapeHtml(message)}</p></div>`;
  }
}

export function renderCandles(payload, options = {}) {
  const candles = payload.candles || [];
  const metric = ["market_cap", "price", "liquidity"].includes(payload.metric) ? payload.metric : "market_cap";
  const formatValue = metric === "price" ? price : money;
  const metricLabel = metric === "liquidity" ? "Liquidity" : metric === "price" ? "Price" : "Market Cap";
  const interval = Number(payload.interval_seconds) || 1;
  const windowSize = Math.max(30, Math.min(500, Number(options.windowSize) || 500));
  const priceZoom = Math.max(0.45, Math.min(5, Number(options.priceZoom) || 1));
  $("snapshot-count").textContent = `${payload.snapshot_count || 0} snapshots`;
  $("last-updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  $("chart-range").textContent = "-";
  const chart = $("chart");
  const empty = $("chart-empty");
  if (!candles.length) {
    chart.innerHTML = "";
    empty.classList.remove("hidden");
    empty.textContent = "No local candles yet for this token.";
    return;
  }
  empty.classList.add("hidden");
  const points = candles
    .slice(-windowSize)
    .map((candle) => ({
      time: Number(candle.time),
      open: Number(candle.open ?? candle.close),
      high: Number(candle.high ?? candle.close),
      low: Number(candle.low ?? candle.close),
      close: Number(candle.close),
      color: candle.color,
    }))
    .filter((point) => {
      if (!Number.isFinite(point.time) || !Number.isFinite(point.close)) return false;
      if (metric === "liquidity") return true;
      return Number.isFinite(point.open) && Number.isFinite(point.high) && Number.isFinite(point.low);
    });

  if (points.length < 1 || (metric === "liquidity" && points.length < 2)) {
    chart.innerHTML = "";
    empty.classList.remove("hidden");
    empty.textContent = metric === "liquidity"
      ? "Need at least two local snapshots to draw a liquidity line."
      : "Need at least one local snapshot to draw a candle.";
    return;
  }

  const width = 1000;
  const height = 390;
  const pad = { left: 54, right: 92, top: 24, bottom: 54 };
  const values = metric === "liquidity"
    ? points.map((point) => point.close)
    : points.flatMap((point) => [
      Number.isFinite(point.open) ? point.open : point.close,
      Number.isFinite(point.high) ? point.high : point.close,
      Number.isFinite(point.low) ? point.low : point.close,
      point.close,
    ]);
  const rawHigh = Math.max(...values);
  const rawLow = Math.min(...values);
  const rawSpan = Math.max(rawHigh - rawLow, Math.abs(rawHigh) * 0.003, 0.000000001);
  const center = (rawHigh + rawLow) / 2;
  const span = rawSpan * priceZoom;
  const high = center + span / 2;
  const low = center - span / 2;
  const first = points[0].close;
  const last = points[points.length - 1].close;
  const change = first ? ((last - first) / first) * 100 : 0;
  const quality = payload.quality || {};
  const sourceLabel = quality.trade_stream_active ? "swap ticks" : "sampled quotes";
  const warningLabel = quality.warning ? ` | ${quality.warning}` : "";
  $("chart-range").textContent = `${metricLabel}: ${formatValue(low)} - ${formatValue(high)} | ${pct(change)} | ${interval}s ${sourceLabel}${warningLabel}`;

  const timeValues = points.map((point) => point.time).filter(Number.isFinite);
  const minTime = Math.min(...timeValues);
  const maxTime = Math.max(...timeValues);
  const timeSpan = Math.max(maxTime - minTime, interval, 1);
  const xStep = points.length === 1 ? 8 : Math.max(3, (width - pad.left - pad.right) / Math.min(points.length, windowSize));
  const yFor = (value) => pad.top + ((high - value) / span) * (height - pad.top - pad.bottom);
  const xFor = (index) => {
    if (points.length === 1) return width / 2;
    const timeOffset = Number.isFinite(points[index]?.time) ? points[index].time - minTime : index;
    return pad.left + (timeOffset / timeSpan) * (width - pad.left - pad.right);
  };

  if (window.LightweightCharts?.createChart) {
    renderFinancialChart(chart, points, {
      metric,
      metricLabel,
      formatValue,
      high,
      low,
    });
    return;
  }

  const chartBody = metric === "liquidity"
    ? renderLiquidityLine(points, xFor, yFor, pad, height, width)
    : renderPriceCandlesticks(points, xFor, yFor, xStep);
  const priceAxis = renderPriceAxis(formatValue, high, low, span, yFor, width, pad);
  const timeAxis = renderTimeAxis(points, xFor, height, pad);

  chart.innerHTML = `
    <svg class="price-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img" aria-label="Local token ${metricLabel.toLowerCase()} ${metric === "liquidity" ? "line" : "candlesticks"}">
      <line class="chart-cross-line" x1="${pad.left}" y1="${pad.top}" x2="${width - pad.right}" y2="${pad.top}" />
      <line class="chart-cross-line" x1="${pad.left}" y1="${height / 2}" x2="${width - pad.right}" y2="${height / 2}" />
      <line class="chart-cross-line" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
      <line class="chart-axis-line" x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
      <line class="chart-axis-line" x1="${width - pad.right}" y1="${pad.top}" x2="${width - pad.right}" y2="${height - pad.bottom}" />
      ${chartBody}
      ${priceAxis}
      ${timeAxis}
      <line class="chart-last-price-line" x1="${pad.left}" y1="${yFor(last).toFixed(1)}" x2="${width - pad.right}" y2="${yFor(last).toFixed(1)}" />
      <text class="chart-last-price" x="${width - pad.right + 10}" y="${yFor(last).toFixed(1)}">${formatValue(last)}</text>
    </svg>
  `;
  attachChartWheelHandlers(chart);
}

function renderFinancialChart(chart, points, options) {
  const seriesKind = options.metric === "liquidity" ? "line" : "candlestick";
  const canReuseChart = chart.__mtpChart && chart.__mtpSeries && chart.__mtpSeriesKind === seriesKind;
  if (chart.__mtpChart && !canReuseChart) {
    chart.__mtpChart.remove();
    chart.__mtpChart = null;
    chart.__mtpSeries = null;
    chart.__mtpSeriesKind = null;
  }
  if (chart.__mtpResizeObserver && !canReuseChart) {
    chart.__mtpResizeObserver.disconnect();
    chart.__mtpResizeObserver = null;
  }
  chart.onwheel = null;
  const library = window.LightweightCharts;
  let financialChart = chart.__mtpChart;
  let series = chart.__mtpSeries;
  const isNewChart = !canReuseChart;
  if (isNewChart) {
    chart.innerHTML = "";
    financialChart = library.createChart(chart, {
      autoSize: true,
      layout: {
        background: { type: library.ColorType.Solid, color: "#0b0f16" },
        textColor: "#9ba3b4",
        fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        fontSize: 12,
      },
      grid: {
        vertLines: { color: "rgba(238, 243, 255, 0.09)" },
        horzLines: { color: "rgba(238, 243, 255, 0.11)" },
      },
      rightPriceScale: {
        visible: true,
        borderColor: "rgba(238, 243, 255, 0.18)",
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        visible: true,
        borderColor: "rgba(238, 243, 255, 0.18)",
        timeVisible: true,
        secondsVisible: true,
        fixLeftEdge: false,
        fixRightEdge: false,
        rightOffset: 4,
        barSpacing: 5,
        minBarSpacing: 1,
      },
      crosshair: {
        mode: library.CrosshairMode.Normal,
        vertLine: { color: "rgba(238, 243, 255, 0.32)", width: 1, style: 3 },
        horzLine: { color: "rgba(238, 243, 255, 0.32)", width: 1, style: 3 },
      },
      localization: {
        priceFormatter: options.formatValue,
      },
    });
    series = seriesKind === "line"
      ? financialChart.addSeries(library.LineSeries, {
        color: "#5f7cff",
        lineWidth: 2,
        priceLineColor: "#5f7cff",
        priceLineWidth: 1,
        priceLineStyle: 2,
      })
      : financialChart.addSeries(library.CandlestickSeries, {
        upColor: "#5ee0a5",
        downColor: "#ff5f70",
        borderUpColor: "#5ee0a5",
        borderDownColor: "#ff5f70",
        wickUpColor: "#5ee0a5",
        wickDownColor: "#ff5f70",
        priceLineColor: "#ff5f70",
        priceLineWidth: 1,
        priceLineStyle: 2,
      });
    chart.__mtpChart = financialChart;
    chart.__mtpSeries = series;
    chart.__mtpSeriesKind = seriesKind;
  }
  const data = options.metric === "liquidity"
    ? points.map((point) => ({ time: point.time, value: point.close }))
    : points.map((point) => ({
      time: point.time,
      open: point.open,
      high: point.high,
      low: point.low,
      close: point.close,
    }));
  series.setData(data);
  if (isNewChart) {
    financialChart.timeScale().fitContent();
  }
  if (isNewChart && window.ResizeObserver) {
    const observer = new ResizeObserver(() => {
      financialChart.resize(chart.clientWidth || 1000, chart.clientHeight || 390);
    });
    observer.observe(chart);
    chart.__mtpResizeObserver = observer;
  }
}

function renderLiquidityLine(points, xFor, yFor, pad, height, width) {
  const linePoints = points.map((point, index) => `${xFor(index).toFixed(1)},${yFor(point.close).toFixed(1)}`).join(" ");
  const areaPoints = `${pad.left},${height - pad.bottom} ${linePoints} ${width - pad.right},${height - pad.bottom}`;
  return `
    <polygon class="chart-area liquidity-area" points="${areaPoints}" />
    <polyline class="chart-line liquidity-line" points="${linePoints}" />
  `;
}

function renderPriceCandlesticks(points, xFor, yFor, xStep) {
  const candleWidth = Math.max(2.5, Math.min(8, xStep * 0.72));
  const candles = points.map((point, index) => {
    const open = Number.isFinite(point.open) ? point.open : point.close;
    const high = Number.isFinite(point.high) ? point.high : Math.max(open, point.close);
    const low = Number.isFinite(point.low) ? point.low : Math.min(open, point.close);
    const isDown = point.close < open || point.color === "red";
    const x = xFor(index);
    const yOpen = yFor(open);
    const yClose = yFor(point.close);
    const bodyTop = Math.min(yOpen, yClose);
    const rawBodyHeight = Math.abs(yClose - yOpen);
    const isFlat = rawBodyHeight < 1.2;
    const bodyHeight = Math.max(rawBodyHeight, isFlat ? 1.4 : 2);
    const bodyX = x - candleWidth / 2;
    return `
      <line class="chart-wick ${isDown ? "down" : "up"}" x1="${x.toFixed(1)}" y1="${yFor(high).toFixed(1)}" x2="${x.toFixed(1)}" y2="${yFor(low).toFixed(1)}" />
      <rect class="chart-candle ${isFlat ? "chart-flat-candle" : ""} ${isDown ? "down" : "up"}" x="${bodyX.toFixed(1)}" y="${(isFlat ? yClose - bodyHeight / 2 : bodyTop).toFixed(1)}" width="${candleWidth.toFixed(1)}" height="${bodyHeight.toFixed(1)}" rx="0.8" />
    `;
  }).join("");
  return candles;
}

function renderPriceAxis(formatValue, high, low, span, yFor, width, pad) {
  const steps = 6;
  return Array.from({ length: steps }, (_, index) => {
    const value = high - (span * index) / (steps - 1);
    const y = yFor(value);
    return `
      <line class="chart-price-tick" x1="${width - pad.right}" y1="${y.toFixed(1)}" x2="${width - pad.right + 7}" y2="${y.toFixed(1)}" />
      <text class="chart-axis-label price-axis-label" x="${width - pad.right + 12}" y="${(y + 4).toFixed(1)}">${formatValue(value)}</text>
    `;
  }).join("");
}

function renderTimeAxis(points, xFor, height, pad) {
  if (!points.length) return "";
  const labelCount = Math.min(6, points.length);
  const indexes = Array.from({ length: labelCount }, (_, index) => (
    Math.round((points.length - 1) * (index / Math.max(1, labelCount - 1)))
  ));
  return indexes.map((pointIndex) => {
    const point = points[pointIndex];
    const x = xFor(pointIndex);
    return `
      <line class="chart-time-tick" x1="${x.toFixed(1)}" y1="${height - pad.bottom}" x2="${x.toFixed(1)}" y2="${height - pad.bottom + 7}" />
      <text class="chart-axis-label time-axis-label" x="${x.toFixed(1)}" y="${height - 22}">${formatChartTime(point.time)}</text>
    `;
  }).join("");
}

function formatChartTime(timestamp) {
  const date = new Date(Number(timestamp) * 1000);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function attachChartWheelHandlers(chart) {
  chart.onwheel = (event) => {
    const rect = chart.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const region = x > rect.width - 120 ? "price" : y > rect.height - 74 ? "time" : "";
    if (!region || typeof window.adjustChartViewFromWheel !== "function") return;
    event.preventDefault();
    window.adjustChartViewFromWheel(region, event.deltaY > 0 ? 1 : -1);
  };
}

export function renderDetail(payload) {
  const position = payload.position || {};
  const latest = payload.latest_snapshot || {};
  const trend = payload.trend || {};
  const age = Number(trend.latest_age_seconds);
  const ageLabel = Number.isFinite(age) ? `${Math.round(age)}s ago` : "-";
  renderProtectionRail(payload.protection || {});
  renderSignalRail(payload.signals || {});
  $("position-detail").innerHTML = [
    ["Source", position.source || "-"],
    ["Status", position.status || "-"],
    ["Quote", position.quote_status || "-"],
    ["Price Trend", pct(trend.price_change_pct)],
    ["Liquidity Trend", pct(trend.liquidity_change_pct)],
    ["Holders", position.holder_count || "-"],
    ["Top 10", pct(position.top_10_holder_pct)],
    ["Snapshots", payload.snapshot_count || 0],
    ["Latest Source", trend.latest_source || "-"],
    ["Latest Context", trend.latest_context || "-"],
    ["Latest Age", ageLabel],
    ["Latest Risk", latest.risk_label || "-"],
  ].map(([label, value]) => `
    <div class="detail-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
  `).join("");
}

function riskClassFor(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized.includes("emergency") || normalized.includes("danger") || normalized.includes("fail")) return "danger";
  if (normalized.includes("warn") || normalized.includes("caution")) return "warn";
  return "ok";
}

function renderProtectionRail(protection) {
  const rail = $("protection-rail");
  if (!rail) return;
  const state = protection.state || "UNKNOWN";
  const riskClass = riskClassFor(protection.risk_level || protection.alert_level || state);
  const reasons = (protection.reasons || []).slice(0, 3);
  const extensions = (protection.token_extensions || []).slice(0, 4);
  rail.innerHTML = `
    <div class="protection-status ${riskClass}">
      <span>${escapeHtml(state)}</span>
      <strong>${escapeHtml(protection.risk_level || protection.alert_level || "UNKNOWN")}</strong>
    </div>
    <div class="protection-grid">
      <div><span>Quote</span><strong>${escapeHtml(protection.quote_status || "-")}</strong></div>
      <div><span>Sell Plan</span><strong>${escapeHtml(protection.suggested_sell_pct ? `${protection.suggested_sell_pct}%` : "-")}</strong></div>
      <div><span>Auto Sell</span><strong>LOCKED</strong></div>
      <div><span>Live Action</span><strong>LOCKED</strong></div>
      <div><span>From Peak</span><strong>${pct(protection.price_from_peak_pct)}</strong></div>
      <div><span>Liq Peak</span><strong>${pct(protection.liquidity_from_peak_pct)}</strong></div>
    </div>
    <div class="protection-note">
      <strong>${escapeHtml(protection.token_standard || "Token standard unknown")}</strong>
      <small>${escapeHtml(extensions.length ? extensions.join(", ") : protection.token_mechanics_risk || "No extension data")}</small>
    </div>
    <div class="protection-reasons">
      ${reasons.map((reason) => `<p>${escapeHtml(reason)}</p>`).join("") || "<p>No protection reasons recorded.</p>"}
    </div>
  `;
}

function renderSignalRail(signals) {
  const rail = $("signal-rail");
  if (!rail) return;
  const social = signals.social || [];
  const catalysts = signals.catalysts || [];
  const catalystCards = catalysts.map((item) => `
    <div class="signal-card catalyst">
      <strong>${escapeHtml(item.symbol || shortMint(item.mint))}</strong>
      <p>${escapeHtml(item.summary || "Catalyst card")}</p>
      <small>${escapeHtml((item.sources || []).join(", ") || "local")} | ${escapeHtml(item.snapshot_count ?? 0)} snapshots</small>
    </div>
  `).join("");
  const socialCards = social.map((item) => `
    <div class="signal-card social">
      <strong>${escapeHtml(item.account || "social")}</strong>
      <p>${escapeHtml(item.text || "No text")}</p>
      <small>${escapeHtml((item.keywords || []).join(", ") || "no keywords")}</small>
    </div>
  `).join("");
  rail.innerHTML = catalystCards + socialCards || `
    <div class="signal-card empty">
      <strong>No direct signal match</strong>
      <p>Local social/catalyst records do not yet match this selected mint.</p>
    </div>
  `;
}

export function renderSnapshotFeed(payload) {
  const snapshots = payload.snapshots || [];
  if (!snapshots.length) {
    $("snapshot-feed").innerHTML = `<div class="snapshot-row"><strong>No snapshots</strong><small>Waiting for local token history.</small></div>`;
    return;
  }
  $("snapshot-feed").innerHTML = snapshots.slice(-8).reverse().map((snapshot) => {
    const when = snapshot.time ? new Date(Number(snapshot.time) * 1000).toLocaleTimeString() : "-";
    return `
      <div class="snapshot-row">
        <strong>${escapeHtml(snapshot.context || "snapshot")} <small>${escapeHtml(when)}</small></strong>
        <small>${escapeHtml(snapshot.source || "-")} | ${price(snapshot.price)} | ${money(snapshot.liquidity)}</small>
      </div>
    `;
  }).join("");
}

export function renderIntelPanel(state, options = {}) {
  const preserveFocusedForm = !options.force && shouldKeepActiveFormStable(state.activePanel);
  document.querySelectorAll("[data-panel]").forEach((button) => {
    button.classList.toggle("tab-active", button.dataset.panel === state.activePanel);
  });
  document.querySelectorAll("[data-nav-panel]").forEach((button) => {
    button.classList.toggle("nav-active", button.dataset.navPanel === state.activePanel);
  });
  if (preserveFocusedForm) {
    return;
  }

  if (state.activePanel === "protection") {
    renderProtectionPanel(state);
  } else if (state.activePanel === "signals") {
    renderSignalsPanel(state);
  } else if (state.activePanel === "readiness") {
    renderReadinessPanel(state);
  } else if (state.activePanel === "replay") {
    renderReplayPanel(state);
  } else if (state.activePanel === "portfolio") {
    renderPortfolioPanel(state);
  } else if (state.activePanel === "positions") {
    renderPositionsPanel(state);
  } else if (state.activePanel === "orders") {
    renderOrdersPanel(state);
  } else if (state.activePanel === "holders") {
    renderHoldersPanel(state);
  } else if (state.activePanel === "risk") {
    renderRiskPanel(state);
  } else {
    renderTradesPanel(state);
  }
}

export function shouldKeepActiveFormStable(activePanel, doc = document) {
  const active = doc?.activeElement;
  const formSelector = activePanel === "protection"
    ? ".protection-add-form"
    : activePanel === "signals"
      ? ".social-import-form"
      : "";
  if (!formSelector) return false;
  if (active && typeof active.closest === "function" && active.closest(formSelector)) return true;
  const form = typeof doc?.querySelector === "function" ? doc.querySelector(formSelector) : null;
  if (!form || typeof form.querySelectorAll !== "function") return false;
  return Array.from(form.querySelectorAll("input, textarea")).some((field) => {
    if (field.type === "checkbox") return false;
    return String(field.value || "").trim().length > 0;
  });
}

function selectedPosition(state) {
  return state.positions.find((item) => item.mint === state.selectedMint) || state.positions[0] || {};
}

function renderTradesPanel(state) {
  const trades = state.trades || {};
  const rows = [
    ["Open Trades", trades.open_trades || [], "Active paper positions being monitored."],
    ["Closed Trades", trades.closed_trades || [], "Completed paper exits available for postmortem."],
    ["Failed Trades", trades.failed_trades || [], "Failed fills or rejected paper attempts."],
  ];
  $("intel-grid").innerHTML = rows.map(([title, items, copy]) => `
    <div class="intel-card">
      <strong>${escapeHtml(title)}: ${items.length}</strong>
      <p>${escapeHtml(copy)}</p>
    </div>
  `).join("") + selectedTradeCards(trades.open_trades || []);
}

function renderPortfolioPanel(state) {
  const trades = state.trades || {};
  const open = trades.open_trades || [];
  const closed = trades.closed_trades || [];
  const failed = trades.failed_trades || [];
  const all = open.concat(closed, failed);
  if (!state.selectedPortfolioTradeKey && all.length) {
    state.selectedPortfolioTradeKey = portfolioTradeKey(all[0], 0);
  }
  const selected = findPortfolioTrade(all, state.selectedPortfolioTradeKey) || all[0] || null;
  const openPnl = sumPnl(open);
  const closedPnl = sumPnl(closed);
  const totalPnl = openPnl + closedPnl;
  $("intel-grid").innerHTML = `
    <div class="intel-card portfolio-total-card">
      <strong>Total PnL</strong>
      <p class="${pnlClass(totalPnl)}">${pnlMoney(totalPnl)}</p>
      <small>Open + closed paper trades</small>
    </div>
    <div class="intel-card portfolio-total-card">
      <strong>Open PnL</strong>
      <p class="${pnlClass(openPnl)}">${pnlMoney(openPnl)}</p>
      <small>${open.length} open positions</small>
    </div>
    <div class="intel-card portfolio-total-card">
      <strong>Closed PnL</strong>
      <p class="${pnlClass(closedPnl)}">${pnlMoney(closedPnl)}</p>
      <small>${closed.length} closed trades</small>
    </div>
    <div class="intel-card portfolio-total-card">
      <strong>Failed Attempts</strong>
      <p>${failed.length}</p>
      <small>Failed fills or blocked attempts</small>
    </div>
    ${winnerPatternSection(state.winnerPatterns)}
    ${tradeDetailSection(selected)}
    ${ledgerSection("Open Positions", open, "No open paper positions.", state.selectedPortfolioTradeKey)}
    ${ledgerSection("Closed Trades", closed, "No closed paper trades yet.", state.selectedPortfolioTradeKey)}
    ${ledgerSection("Failed Attempts", failed, "No failed paper attempts.", state.selectedPortfolioTradeKey)}
  `;
  $("intel-grid").querySelectorAll("[data-trade-key]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedPortfolioTradeKey = row.dataset.tradeKey || "";
      renderPortfolioPanel(state);
    });
  });
}

function winnerPatternSection(review) {
  if (!review) {
    return `<div class="intel-card trade-detail-section"><strong>Winner Pattern Review</strong><p>Loading winner pattern review.</p></div>`;
  }
  const traits = (review.repeatable_traits || []).map((trait) => `<p>${escapeHtml(trait)}: ${escapeHtml((review.trait_counts || {})[trait] || 0)}</p>`).join("") || "<p>No repeatable traits yet.</p>";
  const winners = (review.top_winners || []).slice(0, 4).map((trade) => `
    <p>${escapeHtml(trade.symbol || shortMint(trade.mint))} | ${pnlMoney(trade.pnl)} | MC ${money(trade.entry_market_cap)} to ${money(trade.exit_market_cap)}</p>
  `).join("") || "<p>No closed winners yet.</p>";
  const wallets = (review.wallet_leaders || []).slice(0, 4).map((wallet) => `
    <p>${escapeHtml(shortMint(wallet.wallet))} | ${escapeHtml(wallet.wins)} wins | ${pnlMoney(wallet.pnl)}</p>
  `).join("") || "<p>No winner wallet leaders yet.</p>";
  return `
    <div class="intel-card trade-detail-section winner-pattern-section">
      <div class="trade-detail-title">
        <span>
          <strong>Winner Pattern Review</strong>
          <small>${escapeHtml(review.winner_count)} winners / ${escapeHtml(review.loser_count)} losers | live execution locked</small>
        </span>
        <b>${escapeHtml(review.big_winner_count)} big</b>
      </div>
      ${review.sample_warning ? `<p class="warning-copy">${escapeHtml(review.sample_warning)}</p>` : ""}
      <div class="trade-detail-notes">
        <div><strong>Traits To Watch</strong>${traits}</div>
        <div><strong>Top Winners</strong>${winners}</div>
        <div><strong>Wallet Leaders</strong>${wallets}</div>
        <div><strong>Actions</strong>${(review.recommended_actions || []).slice(0, 3).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>
      </div>
    </div>
  `;
}

function ledgerSection(title, rows, empty, selectedKey) {
  const cards = rows.slice(0, 20).map((trade, index) => {
    const mint = trade.token_mint || trade.mint || "";
    const pnl = tradePnl(trade);
    const pnlPct = trade.total_pnl_pct ?? trade.pnl_pct;
    const key = portfolioTradeKey(trade, index);
    return `
      <button class="ledger-row ${selectedKey === key ? "active" : ""}" data-trade-key="${escapeHtml(key)}">
        <span>
          <strong>${escapeHtml(trade.symbol || trade.name || shortMint(mint))}</strong>
          <small>${escapeHtml(shortMint(mint))} | ${escapeHtml(trade.status || "recorded")}</small>
        </span>
        <span><small>PnL</small><strong class="${pnlClass(pnl)}">${pnlMoney(pnl)}</strong></span>
        <span><small>PnL %</small><strong class="${pnlClass(pnlPct)}">${pct(pnlPct)}</strong></span>
        <span><small>Size</small><strong>${money(trade.size_usd ?? trade.entry_value)}</strong></span>
        <span><small>Market Cap</small><strong>${money(trade.current_market_cap ?? trade.market_cap)}</strong></span>
        <span><small>Reason</small><strong>${escapeHtml(trade.exit_reason || trade.close_reason || trade.failure_reason || trade.entry_reason || trade.reason || "-")}</strong></span>
      </button>
    `;
  }).join("");
  return `
    <div class="intel-card ledger-section">
      <strong>${escapeHtml(title)}: ${rows.length}</strong>
      <div class="ledger-list">
        ${cards || `<div class="ledger-empty">${escapeHtml(empty)}</div>`}
      </div>
    </div>
  `;
}

function tradeDetailSection(trade) {
  if (!trade) {
    return `
      <div class="intel-card trade-detail-section">
        <strong>Selected Trade Detail</strong>
        <p>No trade selected.</p>
      </div>
    `;
  }
  const mint = trade.token_mint || trade.mint || "";
  const wallets = (trade.wallets || []).filter(Boolean).map(shortMint).join(", ") || "-";
  const sells = Array.isArray(trade.sells) ? trade.sells.length : 0;
  return `
    <div class="intel-card trade-detail-section">
      <div class="trade-detail-title">
        <span>
          <strong>${escapeHtml(trade.symbol || trade.name || shortMint(mint))}</strong>
          <small>${escapeHtml(shortMint(mint))} | ${escapeHtml(trade.status || "recorded")} | ${escapeHtml(trade.paper_lane || (trade.exploration ? "exploration" : "main"))}</small>
        </span>
        <b class="${pnlClass(tradePnl(trade))}">${pnlMoney(tradePnl(trade))}</b>
      </div>
      <div class="trade-detail-grid">
        ${detailMetric("MC In", money(trade.entry_market_cap ?? trade.market_cap_at_entry))}
        ${detailMetric("MC Out / Now", money(trade.exit_market_cap ?? trade.market_cap_at_exit ?? trade.current_market_cap ?? trade.market_cap))}
        ${detailMetric("Entry Price", price(trade.entry_price ?? trade.quoted_entry_price))}
        ${detailMetric("Exit / Current Price", price(trade.exit_price ?? trade.close_price ?? trade.current_price))}
        ${detailMetric("Entry Liq", money(trade.entry_liquidity_usd ?? trade.liquidity_usd))}
        ${detailMetric("Current Liq", money(trade.current_liquidity_usd ?? trade.liquidity_usd))}
        ${detailMetric("Size", money(trade.size_usd ?? trade.entry_value))}
        ${detailMetric("PnL %", pct(trade.total_pnl_pct ?? trade.pnl_pct), pnlClass(trade.total_pnl_pct ?? trade.pnl_pct))}
        ${detailMetric("Remaining", trade.remaining_pct == null ? "-" : pct(trade.remaining_pct))}
        ${detailMetric("Fees", money(trade.total_fees_usd ?? trade.entry_fee_usd))}
        ${detailMetric("Opened", escapeHtml(trade.entry_time_iso || formatTradeTime(trade.entry_time)))}
        ${detailMetric("Closed", escapeHtml(trade.close_time_iso || trade.exit_time_iso || formatTradeTime(trade.close_time)))}
      </div>
      <div class="trade-detail-notes">
        ${detailNote("Entry", trade.entry_reason || trade.reason || "-")}
        ${detailNote("Exit / Failure", trade.exit_reason || trade.close_reason || trade.failure_reason || "-")}
        ${detailNote("Wallets", wallets)}
        ${detailNote("Sells", sells ? `${sells} recorded sell event${sells === 1 ? "" : "s"}` : "No sell events recorded.")}
      </div>
    </div>
  `;
}

function detailMetric(label, value, className = "") {
  return `<div><span>${escapeHtml(label)}</span><strong class="${escapeHtml(className)}">${value}</strong></div>`;
}

function detailNote(label, value) {
  return `<div><strong>${escapeHtml(label)}</strong><p>${escapeHtml(value)}</p></div>`;
}

function portfolioTradeKey(trade, index) {
  return `${trade.status || "recorded"}:${trade.token_mint || trade.mint || ""}:${trade.entry_time_iso || trade.close_time_iso || trade.exit_time_iso || index}`;
}

function findPortfolioTrade(trades, key) {
  if (!key) return null;
  return trades.find((trade, index) => portfolioTradeKey(trade, index) === key) || null;
}

function sumPnl(rows) {
  return rows.reduce((total, trade) => total + tradePnl(trade), 0);
}

function tradePnl(trade) {
  const value = trade.total_pnl ?? trade.pnl ?? trade.realized_pnl ?? trade.unrealized_pnl;
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function pnlMoney(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "$0.00";
  const sign = number < 0 ? "-" : "";
  const absolute = Math.abs(number);
  if (absolute >= 1000000) return `${sign}$${(absolute / 1000000).toFixed(2)}M`;
  if (absolute >= 1000) return `${sign}$${(absolute / 1000).toFixed(2)}K`;
  return `${sign}$${absolute.toFixed(2)}`;
}

function pnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "";
  return number > 0 ? "risk-ok" : "risk-danger";
}

function formatTradeTime(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "-";
  const millis = number > 1000000000000 ? number : number * 1000;
  return new Date(millis).toLocaleString();
}

function selectedTradeCards(openTrades) {
  return openTrades.slice(0, 4).map((trade) => `
    <div class="intel-card">
      <strong>${escapeHtml(trade.symbol || trade.name || shortMint(trade.token_mint || trade.mint))}</strong>
      <small>${escapeHtml(shortMint(trade.token_mint || trade.mint))}</small>
      <p>PNL ${pct(trade.total_pnl_pct || trade.pnl_pct)} | ${money(trade.current_market_cap || trade.market_cap)}</p>
    </div>
  `).join("");
}

function renderReplayPanel(state) {
  const decisions = state.decisions || {};
  const decisionRows = decisions.items || [];
  if (decisionRows.length) {
    $("intel-grid").innerHTML = `
      <div class="intel-card trade-detail-section">
        <div class="trade-detail-title">
          <span>
            <strong>Decision Ledger</strong>
            <small>${escapeHtml(decisions.count || decisionRows.length)} recent records | canonical candidate audit trail</small>
          </span>
          <b>LOCKED</b>
        </div>
        <div class="ledger-list">
          ${decisionRows.slice(0, 30).map(decisionRow).join("")}
        </div>
      </div>
    `;
    return;
  }
  const trades = state.trades || {};
  const closed = trades.closed_trades || [];
  const failed = trades.failed_trades || [];
  const rows = closed.concat(failed).slice(-8).reverse();
  $("intel-grid").innerHTML = rows.map((trade) => `
    <div class="intel-card">
      <strong>${escapeHtml(trade.symbol || trade.name || shortMint(trade.token_mint || trade.mint))}</strong>
      <small>${escapeHtml(shortMint(trade.token_mint || trade.mint))}</small>
      <p>PNL ${pct(trade.total_pnl_pct || trade.pnl_pct)} | ${escapeHtml(trade.exit_reason || trade.failure_reason || trade.status || "recorded")}</p>
    </div>
  `).join("") || `<div class="intel-card"><strong>No replay records</strong><p>Closed or failed paper trades will appear here.</p></div>`;
}

function decisionRow(decision) {
  return `
    <div class="ledger-row decision-row">
      <span>
        <strong>${escapeHtml(shortMint(decision.mint))}</strong>
        <small>${escapeHtml(decision.signal_type || "-")} | ${escapeHtml(decision.paper_lane || "-")}</small>
      </span>
      <span><small>Action</small><strong>${escapeHtml(decision.final_action || "-")}</strong></span>
      <span><small>Score</small><strong>${escapeHtml(decision.total_score ?? "-")}</strong></span>
      <span><small>Risk</small><strong>${escapeHtml(decision.risk_label || "-")}</strong></span>
      <span><small>Quotes</small><strong>${quotePair(decision)}</strong></span>
      <span><small>Reason</small><strong>${escapeHtml(decision.action_reason || "-")}</strong></span>
    </div>
  `;
}

function quotePair(decision) {
  const buy = decision.buy_quote_pass === true ? "B+" : decision.buy_quote_pass === false ? "B-" : "B?";
  const sell = decision.sell_quote_pass === true ? "S+" : decision.sell_quote_pass === false ? "S-" : "S?";
  return `${buy}/${sell}`;
}

function renderPositionsPanel(state) {
  $("intel-grid").innerHTML = state.positions.slice(0, 12).map((position) => `
    <div class="intel-card">
      <strong>${escapeHtml(position.label || shortMint(position.mint))}</strong>
      <small>${escapeHtml(shortMint(position.mint))} | ${escapeHtml(position.source || "-")}</small>
      <p>${escapeHtml(position.status || "-")} | ${money(position.market_cap)} | PNL ${pct(position.pnl_pct)}</p>
    </div>
  `).join("") || `<div class="intel-card"><strong>No positions</strong><p>No paper or protected positions are loaded.</p></div>`;
}

function renderOrdersPanel(state) {
  const position = selectedPosition(state);
  $("intel-grid").innerHTML = `
    <div class="intel-card">
      <strong>Buy More</strong>
      <p>Locked. Future add-position actions must pass paper evidence and execution safety gates.</p>
    </div>
    <div class="intel-card">
      <strong>Exit Early</strong>
      <p>Locked. Protection advice is visible, but no live sell route is enabled here.</p>
    </div>
    <div class="intel-card">
      <strong>Selected</strong>
      <small>${escapeHtml(shortMint(position.mint))}</small>
      <p>${escapeHtml(position.source || "-")} | Quote ${escapeHtml(position.quote_status || "-")}</p>
    </div>
  `;
}

function renderHoldersPanel(state) {
  const position = selectedPosition(state);
  const detail = state.selectedDetail || {};
  const protection = detail.protection || {};
  $("intel-grid").innerHTML = `
    <div class="intel-card">
      <strong>Holders</strong>
      <p>${escapeHtml(position.holder_count || "-")} tracked locally.</p>
    </div>
    <div class="intel-card">
      <strong>Top 10</strong>
      <p>${pct(position.top_10_holder_pct)}</p>
    </div>
    <div class="intel-card">
      <strong>Liquidity From Peak</strong>
      <p>${pct(protection.liquidity_from_peak_pct)}</p>
    </div>
    <div class="intel-card">
      <strong>Next Gap</strong>
      <p>Holder cluster analysis exists, but is not fully wired into this desktop panel yet.</p>
    </div>
  `;
}

function renderRiskPanel(state) {
  const detail = state.selectedDetail || {};
  const protection = detail.protection || {};
  const reasons = protection.reasons || [];
  $("intel-grid").innerHTML = `
    <div class="intel-card">
      <strong>${escapeHtml(protection.risk_level || protection.state || "UNKNOWN")}</strong>
      <p>${escapeHtml(protection.reason || "No protection reason recorded.")}</p>
    </div>
    <div class="intel-card">
      <strong>Token Mechanics</strong>
      <p>${escapeHtml(protection.token_mechanics_risk || "-")} | ${escapeHtml(protection.token_standard || "-")}</p>
    </div>
    <div class="intel-card">
      <strong>Extensions</strong>
      <p>${escapeHtml((protection.token_extensions || []).join(", ") || "-")}</p>
    </div>
  ` + reasons.slice(0, 5).map((reason) => `
    <div class="intel-card">
      <strong>Reason</strong>
      <p>${escapeHtml(reason)}</p>
    </div>
  `).join("");
}

function renderProtectionPanel(state) {
  const items = (state.watchlist && state.watchlist.items) || [];
  const form = `
    <div class="intel-card trade-detail-section add-protection-section">
      <strong>Add Protected Token</strong>
      <form class="protection-add-form" onsubmit="window.addProtectedTokenFromDesktop(event)">
        <label><span>Token Mint / CA</span><input name="mint" placeholder="Paste contract address" required /></label>
        <label><span>Your Wallet</span><input name="wallet" placeholder="optional" /></label>
        <label><span>Token Amount</span><input name="amount" placeholder="optional" inputmode="decimal" /></label>
        <label><span>Decimals</span><input name="decimals" value="6" inputmode="numeric" /></label>
        <label><span>Raw Amount</span><input name="raw" placeholder="optional" inputmode="numeric" /></label>
        <label><span>Exit Priority</span><select name="exit_priority"><option value="">normal</option><option value="immediate">immediate</option></select></label>
        <label class="inline-check"><input name="test" type="checkbox" /> <span>Mark amount as test/simulated</span></label>
        <button type="submit">Add / Update Watch</button>
      </form>
      ${state.protectionFormStatus ? `<p class="risk-ok">${escapeHtml(state.protectionFormStatus)}</p>` : ""}
      ${state.protectionFormError ? `<p class="risk-danger">${escapeHtml(state.protectionFormError)}</p>` : ""}
      <small>Watch and alert only. This cannot sell or enable auto-sell.</small>
    </div>
  `;
  $("intel-grid").innerHTML = form + ((items.length ? items : []).slice(0, 8).map((item) => {
    const level = item.alert_level || item.risk_level || item.status || "UNKNOWN";
    const riskClass = String(level).toLowerCase().includes("emergency") || String(level).toLowerCase().includes("danger")
      ? "risk-danger"
      : "risk-ok";
    return `
      <div class="intel-card">
        <strong>${escapeHtml(item.symbol || item.name || shortMint(item.token_mint || item.mint))}</strong>
        <small>${escapeHtml(shortMint(item.token_mint || item.mint))}</small>
        <p class="${riskClass}">${escapeHtml(level)}</p>
        <p>Liquidity ${money(item.current_liquidity)} | Quote ${escapeHtml((item.prepared_exit || {}).quote_status || "-")}</p>
      </div>
    `;
  }).join("") || `<div class="intel-card"><strong>No protected positions</strong><p>Manual protection watchlist is empty.</p></div>`);
}

function renderSignalsPanel(state) {
  const socialItems = ((state.social && state.social.items) || []).slice(0, 4);
  const catalystItems = ((state.catalysts && state.catalysts.items) || []).slice(0, 4);
  const selected = selectedPosition(state);
  const form = `
    <div class="intel-card trade-detail-section social-import-section">
      <strong>Social / Tweet Import</strong>
      <form class="social-import-form" onsubmit="window.importSocialFromDesktop(event)">
        <label><span>Mint / CA</span><input name="mint" value="${escapeHtml(selected.mint || "")}" placeholder="Token mint or CA" /></label>
        <label><span>Account</span><input name="account" placeholder="@account or source" /></label>
        <label><span>Tweet / Post URL</span><input name="url" placeholder="https://x.com/.../status/..." /></label>
        <label><span>Keywords</span><input name="keywords" placeholder="comma-separated" /></label>
        <label class="social-text"><span>Tweet / Signal Text</span><textarea name="text" placeholder="Paste tweet or social signal text" required></textarea></label>
        <button type="submit">Import Signal</button>
      </form>
      ${state.socialFormStatus ? `<p class="risk-ok">${escapeHtml(state.socialFormStatus)}</p>` : ""}
      ${state.socialFormError ? `<p class="risk-danger">${escapeHtml(state.socialFormError)}</p>` : ""}
      <small>Saved as local research through /api/social/import. This does not trigger trades.</small>
    </div>
  `;
  const socialCards = socialItems.map((item) => `
    <div class="intel-card">
      <strong>${escapeHtml(item.account || item.platform || "Social signal")}</strong>
      <p>${escapeHtml(item.text || item.summary || "No text")}</p>
    </div>
  `).join("");
  const catalystCards = catalystItems.map((item) => `
    <div class="intel-card">
      <strong>${escapeHtml(item.symbol || item.name || shortMint(item.mint))}</strong>
      <p>${escapeHtml(catalystSummary(item))}</p>
    </div>
  `).join("");
  $("intel-grid").innerHTML = form + (socialCards + catalystCards || `<div class="intel-card"><strong>No social/catalyst data</strong><p>Import or generate signals to populate this panel.</p></div>`);
}

function catalystSummary(item) {
  if (!item || typeof item !== "object") return "Catalyst card";
  if (typeof item.summary === "string" && item.summary.trim()) return item.summary;
  if (typeof item.outcome === "string" && item.outcome.trim()) return item.outcome;
  if (item.outcome && typeof item.outcome === "object") {
    return item.outcome.summary || item.outcome.reason || item.outcome.verdict || "Catalyst card";
  }
  return item.reason || item.verdict || "Catalyst card";
}

function renderReadinessPanel(state) {
  const readiness = state.readiness || {};
  const rows = readiness.rows || [];
  $("intel-grid").innerHTML = `
    <div class="intel-card">
      <strong>Overall: ${escapeHtml(readiness.overall || "UNKNOWN")}</strong>
      <p>OK ${escapeHtml((readiness.counts || {}).OK || 0)} | WARN ${escapeHtml((readiness.counts || {}).WARN || 0)} | FAIL ${escapeHtml((readiness.counts || {}).FAIL || 0)}</p>
    </div>
  ` + rows.slice(0, 10).map((row) => `
    <div class="intel-card">
      <strong>${escapeHtml(row.check)}: ${escapeHtml(row.status)}</strong>
      <p>${escapeHtml(row.detail)}</p>
    </div>
  `).join("");
}
