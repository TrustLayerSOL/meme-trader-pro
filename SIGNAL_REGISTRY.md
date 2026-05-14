# Signal Registry

Last updated: 2026-05-14

Status values:

- `experimental`: tracked but not proven.
- `validated`: has enough repeatable evidence and baseline comparison.
- `rejected`: failed review or was unsafe/unusable.
- `watchlist`: useful to observe, not yet used for scoring.

## Current Signals

| Signal | Definition | Source | Timestamp availability | Why it may matter | Decision-time safe | Status |
| --- | --- | --- | --- | --- | --- | --- |
| Wallet ROI | Average paper outcome attributed to a wallet after observed signals. | `data/wallet_performance.json`, `data/wallet_quant_report.json` | After paper outcomes close; not available for the original decision unless prior history only is used. | Measures whether wallet-following has produced positive downstream results. | Yes, only when using history before the signal timestamp. | experimental |
| Wallet win rate | Percent of wallet-attributed paper outcomes that closed positive. | `data/wallet_performance.json`, `data/wallet_behavior.json` | After outcomes close; prior history only for decisions. | Helps identify noisy or consistently bad wallets. | Yes, only when prior history is timestamp-filtered. | experimental |
| Wallet hold duration | Average/median hold time for paper outcomes tied to wallet signals. | `data/wallet_behavior.json`, postmortems | After outcomes close; prior history only for decisions. | Distinguishes quick scalpers, round-trippers, and late exits. | Yes, only when prior history is timestamp-filtered. | experimental |
| Rug association | Wallet participation frequency in rug-like or failed tokens. | `data/wallet_behavior.json`, `data/wallet_outcome_ledger.json` | After token outcome classification. | Penalizes wallets repeatedly appearing in dangerous launches. | Yes, only when prior classified history is used. | experimental |
| Cluster timing | Time span between coordinated wallet entries. | `core.signal_context`, scanner payloads | At signal time. | Fast clusters may indicate coordinated behavior; slow clusters may be noise. | Yes. | experimental |
| Liquidity | Token liquidity at decision time. | scanner market data, `token_snapshots`, signal context | At signal time when available. | Determines fill realism, exit feasibility, and rug vulnerability. | Yes. | experimental |
| Market cap | Token market cap at decision time. | scanner market data, `token_snapshots`, signal context | At signal time when available. | Helps classify token stage and entry risk. | Yes. | experimental |
| Token age | Seconds since launch/pair detection at signal time. | scanner/token-age tracker, market data, signal context | At signal time when available. | Distinguishes launch sniping, early confirmation, and late chasing. | Yes. | experimental |
| Estimated slippage | Expected execution friction at signal time. | quote/route analysis, signal context | At signal time when quote exists. | Prevents fake edge from unrealistic fills. | Yes. | experimental |
| Concentration/risk flags | Holder concentration, hard blocks, token mechanics, risk label. | scanner, watchdog, token inspector, signal context | At signal time when checked. | Filters unsafe mechanics and concentrated supply. | Yes. | experimental |
| Market regime | Tags such as runner-heavy, low-liquidity, rug-heavy, dead market, high volatility. | `core.signal_context.classify_market_regime` | At signal time from available market/risk fields. | Helps compare wallet performance across conditions. | Yes, if generated from current fields only. | experimental |
| Entry timing quality | How early/late wallet entries occur relative to launch and market movement. | wallet behavior report, wallet outcome ledger | After enough signal history; prior history only for decisions. | Measures whether wallets enter before opportunity or after the move. | Yes, only when prior history is timestamp-filtered. | experimental |
| Rejection reason | Machine-readable or ranked reason a signal was skipped. | `data/rejected_signals/rejections.jsonl`, `analysis.rejection_hooks` | At decision time. | Lets filters be audited against later outcomes. | Yes. | experimental |
| Later token outcome | Outcome label after the signal: `runner`, `rug`, `dead`, `loser`, `open`, or `unknown`, plus classification reasons and confidence. | `research.outcome_labeler`, paper trades, postmortems, wallet outcome ledger | Future label only. | Used for evaluation and scoring calibration. | No for decision input; yes as separated evaluation label. | experimental |

## Registry Rules

No new signal should be added without:

- a hypothesis,
- source path,
- timestamp availability,
- decision-time safety assessment,
- experiment-log entry,
- baseline comparison plan.
