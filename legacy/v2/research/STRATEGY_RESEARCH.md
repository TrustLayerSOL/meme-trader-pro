# MemeTraderPro Strategy Research

Last updated: 2026-05-13

## Strategic Lane

MemeTraderPro should prioritize post-launch confirmation trading, not pure 3-4 second launch sniping.

The target entry window is roughly 30-180 seconds after launch, after the first bot spike has exposed whether the token has real follow-through. This fits the current product advantage: wallet intelligence, flow checks, replay, paper learning, and aggressive exit management.

## Launch Phases

- 0-30s: bot/bundle discovery phase. Treat as noisy and hostile.
- 30s-3m: confirmation window. Look for resilient price, repeated real buyers, liquidity holding, and sell-route viability.
- 3-10m: curve-completion/migration race. Needs different logic.
- Post-migration: better routing and access, but also more insider exit liquidity.
- Decay: volume contracts, sell dominance grows, holders flatten.

## Rules To Backtest

- Age: evaluate from 30s to 180s by default.
- Market cap: prefer roughly $12k-$55k or 15%-75% bonding curve progress when that data is available.
- Transactions: last 60s should show 25+ swaps and 15+ unique trading wallets when available.
- Buy/sell pressure: buy volume / sell volume around 1.3x-3.5x. Too low is weak; too high may be no sell-test/manipulation.
- Holder growth: net holders up 10-25+ in the last minute. Avoid volume rising while holders stall.
- Price structure: hold above 30s VWAP/EMA, higher low, drawdown from local high below 30-35%.
- Distribution: no single non-system wallet above 4-5%; top 10 unlinked holders below 20-25%; linked cluster below 10-15%.
- Exit feasibility: bot sell size below 10-20% of last-minute sell volume, projected price impact below 8-12%.

## Continuation Pattern

Prefer entries where at least four of these six are true:

- Two consecutive 15s windows have positive net SOL inflow.
- Unique buyers increase faster than unique sellers.
- Sell bursts are absorbed without breaking VWAP.
- Holder count rises while top-holder concentration falls or stays flat.
- Creator/dev/early-bundle wallet has not materially reduced position.
- Transaction frequency stays steady after the first spike.

## Hard Rejects

- Creator/dev wallet sells meaningful amount in first 3m.
- Bundled launch above 10-15% supply; hard reject above 20%.
- Multiple top wallets funded by same source or equal-sized funding.
- One wallet or linked cluster contributes 25-35%+ of early buy volume.
- Top-holder cluster sells in sequence after retail appears.
- Mint/freeze authority, LP authority, or migration status cannot be verified.
- Price drops 35-45% from post-entry high inside confirmation window.
- Volume rises while unique holders do not.

## Exit Rules

- Initial stop: -25% to -35%, or immediate exit on dev/cluster sell.
- First take profit: sell 35-50% at +60% to +100%.
- Second take profit: sell 25-35% at +150% to +250%.
- Runner: trail by 20-30%, tightening to 12-18% after volume contraction or failed higher high.
- Time stop: if no new high within 60-90s after entry, exit or cut half.
- Liquidity stop: exit if projected sell price impact doubles from entry estimate.
- Never average down fresh memes.

## Implementation Buckets

- `flow_score`: net buy pressure, tx frequency stability, unique buyer/seller ratio.
- `structure_score`: VWAP hold, higher low, drawdown control.
- `distribution_score`: holders, top-wallet concentration, linked-wallet/bundle detection.
- `exit_score`: liquidity depth, sell route reliability, projected price impact.

## Implementation coverage (living map)

Rough mapping from this note to shipped behavior — use Replay / Decision Ledger outcomes to prove lift, not the checklist alone.

| Theme | Where it lives | Notes |
| --- | --- | --- |
| Post-launch confirmation bias | `core/scanner.py`, `core/settings_manager.py` & mode thresholds | Confirmation vs sniper via scoring + thresholds. |
| Flow / liquidity / pair quality (hot-feed lane) | `core/market_radar.py`, `MarketRadar` gates | Dex-screener style scoring; Jupiter quotes for route when allowed. |
| Wallet signal + performance memory | `core/scanner.py`, `core/scoring_engine.py`, `core/wallet_performance.py` | Main lane attribution. |
| Risk + Token-2022 | `core/anti_rug.py`, `core/token_inspector.py`, scanner rug merge | Hard blocks recorded on decision payloads. |
| Holder concentration | `core/holder_concentration.py`, `Scanner.evaluate_holder_cluster_risk`, `scanner.apply_holder_cluster_to_rug_result` | Quote-worthy RPC pass; danger hard-blocks paper. |
| True linked-wallet / funder graph | `Scanner.wallet_cluster_risk_context` → `linked_wallet_risk` | Explicit `NOT_CHECKED` / `no_linked_wallet_graph_source` until a graph source ships. |
| Market Radar lane: holder + linkage | `evaluate_market_radar_holder_cluster`, `market_radar_holder_cluster_placeholder`, `market_radar_linked_wallet_placeholder` | Default: no RPC (`UNKNOWN` placeholders). Opt-in bounded `getTokenLargestAccounts` before quotes; `DANGER` hard-blocks without Jupiter. Linkage stays `NOT_CHECKED` on the Dex-only lane. |
| Exit / sizing / paper bookkeeping | `paper_trader.py`, `core/exit_advisor.py`, `ExecutionEngine` | Paper parity; exits before live. |
| Decision lineage | `core/decision_ledger.py`, `core/paper_trade_decision_ids.py` | Canonical records + synthetic legacy IDs where needed. |

## Sources

- Pump.fun public docs: https://github.com/pump-fun/pump-public-docs/blob/main/docs/PUMP_PROGRAM_README.md
- Pump.fun migration docs: https://deepwiki.com/pump-fun/pump-public-docs/7.3-mayhem-fee-recipients
- CoinGecko Q1 2025 report: https://assets.coingecko.com/reports/2025/CoinGecko-2025-Q1-Crypto-Industry-Report.pdf
- KuCoin/Odaily Dune note on graduation rate: https://www.kucoin.com/news/flash/pump-fun-meme-coin-graduation-rate-hits-2-01-highest-since-july-2025
- SolRugDetector: https://arxiv.org/abs/2603.24625
- MemeTrans: https://arxiv.org/abs/2602.13480
- Trust Dynamics and Bot-Driven Responses: https://faculty.washington.edu/weicaics/paper/papers/YueyaoLYHC2025.pdf
- Noir Vector exit/liquidity article: https://noirvector.dev/why-most-solana-meme-coin-bots-lose-liquidity-slippage-and-the-exit-problem/
