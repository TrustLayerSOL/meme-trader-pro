# Historical Rule Discovery Status

Why this was run: forward data exposed FDV proxy spikes and showed that a simple 20k threshold is not a durable buy rule.
Data sources inspected: `117`
Historical rows/mints analyzed: `14809 / 14809`
Split design: `60_20_20_chronological`
Selected buy rule: `BROAD_10K_WATCH_20K_BUY`
Selected exit rule: `EXIT_NO_RECLAIM`
Readiness: `rule_candidate_promising_but_needs_live_actionability`
Selected support: `211` historical candidates; holdout support is `0`, so this is not final validation.

Broad buy-side finding: FDV efficiency is the strongest broad family when available, but it needs risk filters and confirmed path safety.
Broad exit-side finding: drawdown reclaim/no-reclaim behavior is the cleanest exit-side framework, with data-resolution caveats.
Limitations: historical features are richer than live hot-path fields; no PnL or profitability claim is made.
Required live/actionability work: confirmed milestones, spike rejection, same-timestamp jump exclusion, early efficiency capture, and drawdown/reclaim state.
Live trading remains disabled.
