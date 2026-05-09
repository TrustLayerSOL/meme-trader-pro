# Position Cockpit Design

Date: 2026-04-30

## Goal

Add an Axiom-style post-entry monitoring screen to MemeTraderPro while preserving the current paper-first and gated-live-execution model.

The cockpit should let the operator monitor a purchased or protected coin in a dense trading-workstation layout with candle-style price movement, market data, risk state, holder data, trade feed, and safe action buttons.

## Scope

Build this first inside the current Streamlit dashboard as a `Position Cockpit` section.

This is a production-useful prototype for the later professional double-click GUI. Streamlit can support the data layout, tabs, safe buttons, and chart-like display. It is not ideal for high-frequency charting, deep canvas interaction, or TradingView-level controls, so the final pro GUI should eventually move this workflow into a more capable desktop/web app stack.

## Layout

The cockpit should follow the Axiom-style reference:

- dark full-width trading workspace,
- compact token header,
- large central candle-style chart area,
- right-side trade/action panel,
- bottom tabs,
- floating recent trade/signal feed.

The token header should show:

- token name/symbol/mint,
- current market cap,
- price,
- liquidity,
- supply if known,
- holder count if known,
- current risk/alert state.

The chart area should initially render candle-style bars from local token snapshots. If there are too few snapshots, it should fall back to a clear empty state instead of pretending precision.

The right action panel should show:

- paper/live mode state,
- position size,
- bought/sold/holding/PnL,
- quote/sell-route feasibility,
- fee/slippage/priority/bribe estimate where available,
- `Prepare Exit Early`,
- `Sim Add Position`,
- disabled placeholders for future real `Sell Now` and `Buy More`.

The bottom tabs should include:

- Trades,
- Positions,
- Orders / Prepared Actions,
- Holders,
- Top Traders / Wallets,
- Dev / Risk.

## Data Sources

Use existing state first:

- `data/paper_trades.json` for open/closed/failed paper positions,
- `data/manual_watchlist.json` for protected/manual tokens,
- SQLite `token_snapshots` for chart/market/risk history,
- `data/catalyst_cards.json` for thesis/outcome context,
- `data/runtime_status.json` for freshness warnings,
- watchdog holder-concentration fields where available.

No new live order execution should be introduced.

## Actions

`Prepare Exit Early`:

- records a simulated/prepared exit intent,
- marks the token for protection review,
- does not execute a sell,
- uses the same safety language as the watchdog prepared-exit flow.

`Sim Add Position`:

- records a simulated add-position intent,
- does not execute a buy,
- can later feed replay/postmortem analysis.

Future real buttons must remain disabled until:

- execution safety gate passes,
- user explicitly arms live mode,
- quote checks pass,
- audit logs are written,
- kill-switch behavior exists.

## Error Handling

- If runtime state is stale, show a visible warning.
- If chart data is missing, render an empty chart state.
- If quote data is missing, show `not checked` or `amount missing`.
- Do not hide failures by deleting or rewriting runtime state.
- Redact secrets from any displayed errors.

## Testing

Minimum verification:

- compile changed Python files,
- run `python3 -m unittest discover`,
- run `trading_env/bin/python -m unittest discover`,
- confirm Streamlit returns HTTP 200,
- verify runtime heartbeats remain fresh after restart if dashboard code changes.

## Explicit Non-Goals

- No live sell button yet.
- No live buy-more button yet.
- No automatic auto-sell.
- No TradingView-level charting inside Streamlit.
- No major frontend stack migration in this pass.
