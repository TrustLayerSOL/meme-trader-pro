import { importSocialSignal, loadCoreState, loadDecisionExplanation, loadTokenState, saveProtectedToken } from "./api.js";
import { $ } from "./format.js";
import {
  renderCandles,
  renderDetail,
  renderIntelPanel,
  renderOverview,
  renderPositions,
  renderSelectedPosition,
  renderSnapshotFeed,
  renderTokenError,
  renderTokenLoading,
} from "./render.js";

const state = {
  overview: null,
  positions: [],
  selectedMint: null,
  activePanel: "portfolio",
  trades: null,
  watchlist: null,
  social: null,
  catalysts: null,
  readiness: null,
  winnerPatterns: null,
  decisions: null,
  marketRadarReview: null,
  decisionFilter: "all",
  selectedDecisionId: "",
  decisionExplanation: null,
  decisionExplanationDecisionId: "",
  decisionExplanationLoading: false,
  decisionExplanationError: "",
  selectedDetail: null,
  loadingToken: false,
  chartMetric: "market_cap",
  chartInterval: 1,
  chartWindow: 500,
  chartPriceZoom: 1,
  protectionFormStatus: "",
  protectionFormError: "",
  socialFormStatus: "",
  socialFormError: "",
};

async function loadSelectedToken(options = {}) {
  if (state.loadingToken) return;
  state.loadingToken = true;
  renderSelectedPosition(state);
  const showLoading = options.showLoading || !state.selectedDetail;
  if (showLoading) {
    renderTokenLoading();
  }
  try {
    const tokenState = await loadTokenState(
      state.selectedMint,
      state.chartMetric,
      state.chartInterval,
      Math.max(160, state.chartWindow * 2),
    );
    state.selectedDetail = tokenState.detail;
    if (tokenState.detail?.position?.mint) {
      const index = state.positions.findIndex((item) => item.mint === tokenState.detail.position.mint);
      if (index >= 0) {
        state.positions[index] = { ...state.positions[index], ...tokenState.detail.position };
      }
      renderSelectedPosition(state);
      renderPositions(state, selectMint);
    }
    renderCandles(tokenState.candles, {
      windowSize: state.chartWindow,
      priceZoom: state.chartPriceZoom,
    });
    renderDetail(tokenState.detail);
    renderSnapshotFeed(tokenState.snapshots);
    renderIntelPanel(state);
  } catch (error) {
    state.selectedDetail = null;
    renderTokenError(error);
    renderIntelPanel(state);
  } finally {
    state.loadingToken = false;
  }
}

async function selectMint(mint) {
  state.selectedMint = mint;
  state.selectedDetail = null;
  renderPositions(state, selectMint);
  await loadSelectedToken({ showLoading: true });
}

async function loadAll() {
  try {
    const payload = await loadCoreState();
    Object.assign(state, payload);
    if (!state.selectedMint && state.positions.length) {
      state.selectedMint = state.positions[0].mint;
    }
    renderOverview(state);
    renderPositions(state, selectMint);
    renderIntelPanel(state);
    await loadSelectedToken({ showLoading: true });
  } catch (error) {
    $("runtime-pill").textContent = "ERROR";
    $("runtime-pill").className = "status-pill stale";
    $("chart-empty").textContent = `Desktop API error: ${error.message}`;
  }
}

window.addProtectedTokenFromDesktop = async function addProtectedTokenFromDesktop(event) {
  event.preventDefault();
  state.protectionFormStatus = "";
  state.protectionFormError = "";
  const form = event.currentTarget;
  const payload = {
    mint: form.elements.mint.value.trim(),
    wallet: form.elements.wallet.value.trim() || undefined,
    amount: form.elements.amount.value.trim() || undefined,
    decimals: form.elements.decimals.value.trim() || undefined,
    raw: form.elements.raw.value.trim() || undefined,
    test: form.elements.test.checked,
    alert_only: true,
    external_position: true,
    exit_priority: form.elements.exit_priority.value || undefined,
  };
  try {
    const response = await saveProtectedToken(payload);
    state.protectionFormStatus = response.detail || "Protected token added.";
    form.reset();
    form.elements.decimals.value = "6";
    form.elements.test.checked = false;
    state.activePanel = "protection";
    await loadAll();
    renderIntelPanel(state, { force: true });
  } catch (error) {
    state.protectionFormError = error instanceof Error ? error.message : "Unable to add protected token.";
    renderIntelPanel(state, { force: true });
  }
};

window.importSocialFromDesktop = async function importSocialFromDesktop(event) {
  event.preventDefault();
  state.socialFormStatus = "";
  state.socialFormError = "";
  const form = event.currentTarget;
  const payload = {
    mint: form.elements.mint.value.trim() || state.selectedMint || undefined,
    url: form.elements.url.value.trim() || undefined,
    text: form.elements.text.value.trim(),
    account: form.elements.account.value.trim() || undefined,
    keywords: form.elements.keywords.value.trim() || undefined,
  };
  try {
    const response = await importSocialSignal(payload);
    state.socialFormStatus = response.detail || "Social signal imported locally.";
    form.reset();
    state.activePanel = "signals";
    await loadAll();
    state.activePanel = "signals";
    renderIntelPanel(state, { force: true });
  } catch (error) {
    state.socialFormError = error instanceof Error ? error.message : "Unable to import social signal.";
    renderIntelPanel(state, { force: true });
  }
};

window.explainDecisionFromDesktop = async function explainDecisionFromDesktop(decisionId) {
  if (!decisionId || state.decisionExplanationLoading) return;
  state.decisionExplanation = null;
  state.decisionExplanationDecisionId = decisionId;
  state.decisionExplanationError = "";
  state.decisionExplanationLoading = true;
  renderIntelPanel(state, { force: true });
  try {
    state.decisionExplanation = await loadDecisionExplanation(decisionId);
  } catch (error) {
    state.decisionExplanation = null;
    state.decisionExplanationError = error instanceof Error ? error.message : "Unable to explain decision.";
  } finally {
    state.decisionExplanationLoading = false;
    renderIntelPanel(state, { force: true });
  }
};

document.querySelectorAll("[data-panel]").forEach((button) => {
  button.addEventListener("click", () => {
    state.activePanel = button.dataset.panel || "trades";
    renderIntelPanel(state);
  });
});

document.querySelectorAll("[data-nav-panel]").forEach((button) => {
  button.addEventListener("click", () => {
    state.activePanel = button.dataset.navPanel || "trades";
    renderIntelPanel(state);
  });
});

document.querySelectorAll("[data-metric]").forEach((button) => {
  button.addEventListener("click", async () => {
    state.chartMetric = button.dataset.metric || "price";
    document.querySelectorAll("[data-metric]").forEach((item) => {
      item.classList.toggle("active", item.dataset.metric === state.chartMetric);
    });
    await loadSelectedToken({ showLoading: true });
  });
});

document.querySelectorAll("[data-interval]").forEach((button) => {
  button.addEventListener("click", async () => {
    state.chartInterval = Number(button.dataset.interval) || 1;
    document.querySelectorAll("[data-interval]").forEach((item) => {
      item.classList.toggle("active", Number(item.dataset.interval) === state.chartInterval);
    });
    await loadSelectedToken();
  });
});

window.adjustChartViewFromWheel = function adjustChartViewFromWheel(region, direction) {
  if (region === "price") {
    state.chartPriceZoom = Math.max(0.45, Math.min(5, state.chartPriceZoom * (direction > 0 ? 1.15 : 0.87)));
  } else if (region === "time") {
        state.chartWindow = Math.max(30, Math.min(500, Math.round(state.chartWindow * (direction > 0 ? 1.2 : 0.84))));
  }
  loadSelectedToken({ showLoading: false });
};

$("refresh-button").addEventListener("click", loadAll);
loadAll();

setInterval(() => {
  const enabled = $("auto-refresh")?.checked;
  if (enabled && state.selectedMint) {
    loadSelectedToken({ showLoading: false });
  }
}, 1000);
