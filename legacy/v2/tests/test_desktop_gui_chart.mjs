import assert from "node:assert/strict";

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }
}

class FakeElement {
  constructor() {
    this.innerHTML = "";
    this.textContent = "";
    this.classList = new FakeClassList();
    this.onwheel = null;
  }

  querySelectorAll() {
    return [];
  }

  getBoundingClientRect() {
    return { left: 0, top: 0, width: 1000, height: 390 };
  }
}

const elements = new Map();
globalThis.window = globalThis;
globalThis.document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new FakeElement());
    return elements.get(id);
  },
  querySelectorAll() {
    return [];
  },
};

const chartCalls = {
  created: 0,
  removed: 0,
  fitContent: 0,
  candleData: null,
  lineData: null,
};
globalThis.ResizeObserver = class {
  observe() {}
  disconnect() {}
};
globalThis.LightweightCharts = {
  CandlestickSeries: "CandlestickSeries",
  LineSeries: "LineSeries",
  ColorType: { Solid: "solid" },
  CrosshairMode: { Normal: 0 },
  createChart(container, options) {
    chartCalls.created += 1;
    chartCalls.options = options;
    return {
      addSeries(seriesType) {
        return {
          setData(data) {
            if (seriesType === "CandlestickSeries") chartCalls.candleData = data;
            if (seriesType === "LineSeries") chartCalls.lineData = data;
          },
        };
      },
      timeScale() {
        return {
          fitContent() {
            chartCalls.fitContent += 1;
          },
        };
      },
      remove() {
        chartCalls.removed += 1;
      },
      resize() {},
    };
  },
};

const { renderCandles, renderIntelPanel, shouldKeepActiveFormStable } = await import("../desktop_gui/assets/render.js");

renderCandles({
  metric: "market_cap",
  interval_seconds: 1,
  snapshot_count: 4,
  candles: [
    { time: 100, open: 100000, high: 105000, low: 95000, close: 102000, color: "green" },
    { time: 101, open: 102000, high: 102000, low: 102000, close: 102000, color: "green" },
    { time: 102, open: 102000, high: 104000, low: 98000, close: 99000, color: "red" },
    { time: 103, open: 99000, high: 110000, low: 99000, close: 109000, color: "green" },
  ],
}, { windowSize: 120, priceZoom: 1 });

const chartMarkup = elements.get("chart").innerHTML;
assert.equal(chartCalls.created, 1, "chart should use the financial chart renderer when available");
assert.equal(chartCalls.candleData.length, 4, "chart should pass all visible candles into the renderer");
assert.deepEqual(Object.keys(chartCalls.candleData[0]).sort(), ["close", "high", "low", "open", "time"].sort());
assert.ok(!chartMarkup.includes("chart-close-line"), "price chart should not render a misleading connector line");
assert.ok(chartCalls.options.rightPriceScale.visible, "chart should render a right-side value scale");
assert.ok(chartCalls.options.timeScale.visible, "chart should render a bottom time scale");
assert.match(elements.get("chart-range").textContent, /^Market Cap:/);
assert.match(elements.get("chart-range").textContent, /sampled quotes/);

renderCandles({
  metric: "market_cap",
  interval_seconds: 1,
  snapshot_count: 4,
  tick_count: 4,
  quality: { trade_stream_active: true },
  candles: [
    { time: 200, open: 100000, high: 105000, low: 95000, close: 102000, color: "green" },
    { time: 201, open: "bad", high: 106000, low: 95000, close: 103000, color: "green" },
    { time: "bad", open: 103000, high: 107000, low: 101000, close: 106000, color: "green" },
    { time: 202, open: 106000, high: 110000, low: 104000, close: 108000, color: "green" },
  ],
}, { windowSize: 120, priceZoom: 1 });

assert.equal(chartCalls.candleData.length, 2, "chart should drop malformed OHLC candles before calling the renderer");
assert.deepEqual(chartCalls.candleData[0], { time: 200, open: 100000, high: 105000, low: 95000, close: 102000 });
assert.match(elements.get("chart-range").textContent, /swap ticks/);

renderCandles({
  metric: "market_cap",
  interval_seconds: 1,
  snapshot_count: 4,
  candles: [
    { time: 104, open: 109000, high: 112000, low: 108000, close: 111000, color: "green" },
  ],
}, { windowSize: 120, priceZoom: 1 });

assert.equal(chartCalls.created, 1, "auto-refresh should update the existing chart instead of recreating it");
assert.equal(chartCalls.removed, 0, "auto-refresh should not remove the existing chart");
assert.equal(chartCalls.fitContent, 1, "auto-refresh should not reset chart pan/zoom after the initial render");

assert.equal(
  shouldKeepActiveFormStable("protection", {
    activeElement: {
      closest(selector) {
        return selector === ".protection-add-form" ? {} : null;
      },
    },
    querySelector() {
      return null;
    },
  }),
  true,
  "protection form should not be re-rendered while an input is focused",
);

assert.equal(
  shouldKeepActiveFormStable("protection", {
    activeElement: null,
    querySelector(selector) {
      if (selector !== ".protection-add-form") return null;
      return {
        querySelectorAll() {
          return [{ value: "MintTypedBeforeRefresh" }, { value: "" }];
        },
      };
    },
  }),
  true,
  "protection form should not be re-rendered while it contains typed input",
);

assert.equal(
  shouldKeepActiveFormStable("portfolio", {
    activeElement: {
      closest() {
        return {};
      },
    },
    querySelector() {
      return null;
    },
  }),
  false,
  "non-form panels should keep rendering normally",
);

renderIntelPanel({
  activePanel: "replay",
  decisionFilter: "quote_failed",
  selectedDecisionId: "dec_failed_quote",
  decisions: {
    count: 3,
    items: [
      {
        decision_id: "dec_bought",
        mint: "BoughtMint111111111111",
        signal_type: "cluster",
        final_action: "paper_opened",
        action_reason: "cluster confirmed",
        paper_lane: "main",
        total_score: 81,
        risk_label: "LOW",
        buy_quote_pass: true,
        sell_quote_pass: true,
        payload: {
          inputs: { wallets: ["WalletA", "WalletB"] },
          rule_outcomes: { risk: { warnings: [] } },
        },
      },
      {
        decision_id: "dec_failed_quote",
        mint: "QuoteFailMint222222",
        signal_type: "cluster",
        final_action: "skip",
        action_reason: "EXIT LIQUIDITY BLOCK",
        paper_lane: "main",
        total_score: 74,
        risk_label: "WARNING",
        buy_quote_pass: true,
        sell_quote_pass: false,
        payload: {
          inputs: { wallets: ["WalletC"], social_match: { matched: true, reason: "ticker match" } },
          rule_outcomes: {
            risk: { warnings: ["sell route degraded"] },
            scoring: { reasons: ["score ok"] },
          },
          quotes: {
            buy: { reason: "quote_ok" },
            sell: { reason: "price_impact_too_high" },
          },
        },
      },
      {
        decision_id: "dec_explore",
        mint: "ExploreMint3333333",
        signal_type: "cluster",
        final_action: "paper_opened",
        action_reason: "near miss",
        paper_lane: "exploration",
        total_score: 64,
        risk_label: "LOW",
        buy_quote_pass: true,
        sell_quote_pass: true,
      },
    ],
  },
});

const decisionMarkup = elements.get("intel-grid").innerHTML;
assert.match(decisionMarkup, /Decision Ledger/);
assert.match(decisionMarkup, /data-decision-filter="quote_failed" class="active"/);
assert.match(decisionMarkup, /QuoteFailMint222222/);
assert.ok(!decisionMarkup.includes("BoughtMint111111111111"), "quote-failed filter should hide bought decisions");
assert.ok(!decisionMarkup.includes("ExploreMint3333333"), "quote-failed filter should hide exploration decisions");
assert.match(decisionMarkup, /Decision Detail/);
assert.match(decisionMarkup, /price_impact_too_high/);
assert.match(decisionMarkup, /WalletC/);
