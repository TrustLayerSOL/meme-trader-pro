# Competitor Bot Review

Last updated: 2026-04-30

Read-only product research comparing current trading bots against MemeTraderPro's local cockpit direction.

## Scope

This is not a profitability ranking. The market splits into:

- fast execution bots,
- trading terminals,
- copy-trading tools,
- broader Telegram automation.

The most relevant comparison set for MemeTraderPro is Solana/meme-coin tooling.

## Top Competitors

| Bot | Category | Best At | Why It Is Strong | Weaknesses / Risks | Pricing / Access | MemeTraderPro Comparison |
| --- | --- | --- | --- | --- | --- | --- |
| Trojan | Solana Telegram bot + web terminal | Solana-native execution and copy trading | Strong execution UX, sniping, swaps, copy trading, wallet analyzer, MEV settings | Fee drag, wallet custody/import risk, copy-trade latency | Free access; docs cite 1% per successful trade plus priority/bribe costs | Do not race on raw speed. Compete on explainable safety, wallet scoring, paper evidence, and manual protection. |
| BONKbot | Solana Telegram bot | Simple fast Solana trading UX | Jupiter routing, buy/sell, DCA/limit orders, MEV modes, portfolio/PnL | Custodial bot wallet flow, fake-bot/phishing risk, 1% fee plus execution costs | Free setup; 1% successful swap fee | Borrow paste-contract simplicity; keep local-first auditability and avoid blind one-click trading. |
| BullX Neo | Solana/multichain web + Telegram terminal | Configurable degen-terminal execution | Pump.fun/Raydium support, MEV modes, bribes, priority fees, token filters | Fee/bribe/slippage complexity can overwhelm users | Docs cite 1% platform fee; protocol fees/priority/bribe extra | Add all-in simulated fee/cost visibility before every paper/live action. |
| Axiom Trade | Solana web trading terminal | All-in-one serious Solana terminal | Token discovery, wallet/Twitter intel, MEV-aware trading, perps/yield integrations | Less local/control-oriented; fee tiers/rewards can obscure true cost | Public sources cite tiered fees/cashback; verify in-app | Closest future GUI competitor. MTP edge: private local memory, skipped-candidate reasoning, safer gates. |
| GMGN.ai | Solana analytics + trading/copy platform | Smart-money discovery and wallet tracking | Wallet tracking, charts, token momentum, copy trading, API, anti-MEV | Copy-trade bait risk, fee/slippage confusion, API/bot permission risk | Docs cite 1% handling fee plus priority/slippage | MTP should build stronger wallet promotion based on paper evidence and anti-bait labels. |
| Photon | Solana web bot/terminal | Fast visual token discovery | New-token discovery, filters, audits, holdings/PnL, fast buy/sell | Public fee clarity is weaker; speed-first UX encourages low-context entries | Public site emphasizes fast/free access; verify in-app | Borrow fast Token Console feel; add token mechanics, holder concentration, and sell-route feasibility. |
| Banana Gun | Multichain Telegram/web bot | Sniping brand and multichain reach | Auto-sniping, buy/sell, copy trade, limits, private transactions, anti-rug/MEV | Imported/generated wallet risk, prior market security concerns, adverse selection from sniping | No subscription per blog; trading fees apply | Avoid instant-buy defaults. MTP's safer niche is protected manual trades and simulated exits. |
| Maestro | Multichain Telegram sniper/trading bot | Automation breadth | Auto-snipe, copytrade, call-channel scraping, limits, trailing stops, anti-rug/MEV | Complex, call-channel overfitting, fee behavior can surprise users | 1% free tier; premium options cited publicly | Match automation later; first ship repeatable paper validation and postmortems. |
| SolTradingBot | Solana Telegram bot | Baseline Solana bot functionality | Solana DEX trading, sniping, alerts/autobuy, broad DEX integration | Less differentiated vs newer bots; fee drag | Public sources cite 1% fee | Quick CA paste, alerts, and simple controls are table stakes. |
| Stratium | Solana copy-trading bot | Low-fee copy-trading positioning | Curated wallet strategies, non-custodial copy, on-chain performance display, Jito bundles | Strategy survivorship, bait-wallet and latency risk | Site/terms cite 0.1% per trade | Wallet intelligence must include drawdown, sample size, bait/follower-trap labels, paper-copy confidence. |

## Sources

- Trojan docs: https://docs.trojan.com/faqs
- Trojan copy trading: https://docs.trojan.com/terminal-overview/tools-and-widgets/copy-trading-bot
- BONKbot site: https://bonkbot.io/
- BONKbot fee docs: https://docs.bonkbot.io/bonkbot/community-and-support/bonkbot-fee-structure
- CoinGecko Solana Telegram bots overview: https://www.coingecko.com/learn/solana-telegram-trading-bots
- BullX Neo fees: https://bullx.gitbook.io/bullx-neo-docs/fees-and-gas
- Axiom fees docs: https://docs.axiom.trade/getting-started/fees
- Axiom fee explainer: https://www.axiompro.app/fees/
- GMGN fees/settings: https://docs.gmgn.ai/index/gmgn-fees-settings
- Photon site: https://photonsol.io/
- Banana Gun Solana docs: https://banana-gun.gitbook.io/banana-gun-solana
- Banana Gun blog: https://blog.bananagun.io/blog/telegram-trading-bots-how-they-work-what-they-cost-and-why-traders-use-them
- Maestro fees: https://docs.maestrobots.com/faq/fees
- Stratium site: https://www.stratiumsol.com/
- Stratium terms: https://www.stratiumsol.com/terms
- MemeTrans paper: https://arxiv.org/abs/2602.13480
- Solana/Jito MEV paper: https://cnitarot.github.io/papers/imc26_solana.pdf

## Strategic Takeaways

### 1. Do Not Compete On 3-Second Sniping

The crowded part of the market sells raw speed. Trojan, BONKbot, BullX, Banana Gun, Maestro, and Photon already fight there.

MemeTraderPro's stronger lane is:

- explainable candidate decisions,
- paper evidence before live action,
- wallet quality scoring,
- token mechanics/risk inspection,
- protected manual trades,
- simulated/prepared exits,
- local operator control.

### 2. Fee And Slippage Transparency Is A Product Gap

Competitors often fragment total trade cost across:

- bot fee,
- protocol fee,
- priority fee,
- bribe,
- slippage,
- token account rent,
- MEV/private routing settings.

MemeTraderPro should show an all-in estimated cost/drag model before candidate entry and protected-position exits.

### 3. Wallet Intelligence Is The Best Competitive Upgrade

Most competitors have copy trading. Fewer clearly explain whether a wallet is actually worth copying.

High-value MTP wallet features:

- rolling 7d/30d stats,
- median hold time,
- drawdown after wallet entry,
- paper-copy win rate,
- realized/paper PnL,
- follower-trap or bait-wallet labels,
- dev-adjacent labels,
- promotion only after enough sample evidence.

### 4. Manual Protection Can Be A Flagship Differentiator

A pasted-mint watchdog that tracks:

- liquidity drain,
- price collapse,
- holder concentration,
- dev/top-holder sells,
- token mechanics,
- sell-route feasibility,
- prepared paper exits,
- audit logs,

is more differentiated than another fast Telegram bot.

### 5. Holder/Bundle Risk Should Move Up The Priority List

Recent memecoin research emphasizes concentration, time-series behavior, and bundle-level signals. That maps directly to MTP's roadmap and should feed candidate scoring, watchdog alerts, and postmortems.

### 6. MEV Protection Should Be Treated As A Tradeoff

Competitors market MEV protection heavily. MTP should show the practical tradeoff:

- safer/private route,
- slower or more expensive route,
- higher priority/bribe,
- possible failed fill,
- net expected drag.

## Recommended Final-Focus List

1. Add all-in fee/slippage/priority/bribe cost modeling to candidate and protection exits.
2. Finish wallet intelligence labels with rolling performance, sample size, and bait/follower-trap detection.
3. Finish Manual Protection as a flagship workflow.
4. Add holder concentration and bundle-risk signals to candidate scoring and watchdog checks.
5. Tighten explainable skip/entry/postmortem records so every decision has a durable reason.
6. Keep live trading gated until paper evidence and safety controls are strong enough.
