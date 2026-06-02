# MemeTraderPro Descriptive Thesis Synthesis

## Scope

This review consolidates the first six descriptive historical thesis cycles for the strict launch-regime FDV-proxy dataset. It is not a new thesis cycle and does not run or recommend trading, paper trading, execution, threshold optimization, grid search, ML, or thesis promotion.

## Dataset State

- Dataset: strict launch-regime FDV-proxy lifecycle dataset
- Launches: `1,500`
- Snapshots: `18,000`
- Outcomes: `1,500`
- Unknown lifecycle classifications: `0`
- FDV-proxy enrichment: available
- True market cap: unavailable
- Original market-cap thresholds: unusable
- True holder count: unavailable
- Top holder share: unavailable
- Insider share: unavailable
- Bundler share: unavailable
- Confirmed DEX depth: unavailable

FDV-proxy outcomes are sufficient for descriptive lifecycle research, but not sufficient for market-cap threshold claims or strategy claims. The current snapshot fields support early lifecycle behavior analysis, but the available features are shallow relative to the thesis families that likely matter for meme-token launch quality.

## Consolidated Thesis Matrix

| Thesis | Name | Classification | Dataset | Launches | Feature Coverage | Strongest Observed Weak Points | Missing Critical Fields | Actionable | Recommended Status |
|---|---|---|---|---:|---|---|---|---|---|
| T001 | Early Ownership Concentration | `no_signal` | Strict launch-regime FDV-proxy | 1,500 | Creator share 100%; first buyer and sniper proxies 1,198/1,500 usable; holder-state fields unavailable | Available concentration proxies did not produce a stable descriptive signal; first buyer shares cluster tightly near 0.5 | `top_holder_share`, `insider_share`, `bundler_share`; true holder distribution | No | `rerun_after_data_upgrade` |
| T002 | Holder Growth Tempo | `weak_signal` | Strict launch-regime FDV-proxy | 1,500 | `active_wallets`, `buy_count`, `event_count`, `liquidity_proxy` at 100%; `holder_count` at 0% | Weak signal is participation-growth proxy only, not true holder growth | `holder_count`, true holder growth, true holder retention, buyer/seller identity splits | No | `rerun_after_data_upgrade` |
| T003 | Creator Archetype History | `no_signal` | Strict launch-regime FDV-proxy | 1,500 | Creator/deployer, launch metadata, and FDV-proxy outcomes at 100% | Creator history is limited to creators observed inside the strict regime; no broader prior-launch context | Broader chronological launch census, cross-regime creator history, repeated funding links | No | `rerun_after_data_upgrade` |
| T004 | Liquidity Persistence / Depth Proxy | `no_signal` | Strict launch-regime FDV-proxy | 1,500 | Liquidity proxy and bonding-curve post balance at 100%; FDV-proxy outcomes at 100% | The liquidity measure is a bonding-curve reserve proxy, not confirmed DEX depth | Confirmed DEX depth, pool depth, order-book/depth snapshots where applicable | No | `park` |
| T005 | Buy/Sell Flow Baseline | `weak_signal` | Strict launch-regime FDV-proxy | 1,500 | Buy, sell, event, active wallet, unique actor, liquidity proxy, FDV-proxy outcomes at 100% | Simple flow is noisy and outlier-sensitive; useful mainly as a control family | True entity clustering, holder retention, manipulation/entity context | No | `use_as_baseline` |
| T006 | Participation Quality | `no_signal` | Strict launch-regime FDV-proxy | 1,500 | Required participation, activity, liquidity proxy, and FDV-proxy fields at 100% | Ratios did not add descriptive structure beyond raw activity; intensity proxies are not direct manipulation evidence | Entity linkage, true holder state, direct manipulation evidence, true holder concentration | No | `park` |

## Common Pattern Across T001-T006

The only thesis families that showed weak descriptive signal were participation and flow-adjacent:

- T002: `weak_signal`, but based on participation-growth proxies rather than true holder growth.
- T005: `weak_signal`, but explicitly baseline/control only.

The no-signal families were:

- T001: ownership concentration, blocked by missing holder-state fields.
- T003: creator archetype history, constrained by the strict-regime-only creator history window.
- T004: liquidity persistence, limited by a reserve proxy rather than confirmed DEX depth.
- T006: participation quality, showing that activity-per-actor ratios did not add much beyond raw activity counts.

The strongest pattern is that available features are too shallow for the higher-value questions. The current dataset can observe activity counts, actor counts, launch timing, pricing proxies, and bonding-curve reserve proxies. It cannot yet observe the actual holder-state and entity-state questions that matter most:

- Who holds supply over time?
- How concentrated is holder distribution?
- Which holders are linked, funded together, or likely coordinated?
- Does holder retention differ from raw participation?
- Does suspicious early entity behavior explain weak flow effects?

The strict launch regime may also be too narrow for creator history and regime-dependence questions. It is useful as a controlled cohort, but not enough to establish whether the weak flow/participation patterns are stable across broader launch conditions.

FDV-proxy outcomes are acceptable for the next descriptive research stage, provided the reports continue to block true market-cap claims. They are not enough for market-cap threshold labels, tradability claims, or strategy claims.

## Ranked Next Research Paths

### 1. True Holder-State Enrichment

Expected value: highest.

This is the best next path because it directly repairs the biggest blockers in T001 and T002. The first six cycles show that proxy participation fields are not enough. The next useful data upgrade is replay-safe holder-state snapshots over the same launch-relative windows.

Required fields:

- `holder_count`
- holder growth from launch-relative snapshots
- holder retention from early windows
- top holder concentration
- top holder share
- holder distribution summary
- creator/deployer share over time if feasible

Recommended scope:

- Start with a bounded holder-state enrichment pilot on a representative subset.
- Confirm runtime, credit cost, and storage footprint.
- If feasible, enrich the strict 1,500-launch cohort first.
- Then rerun T001 and T002 only.

### 2. Expand Regime / Cohort Coverage

Expected value: medium-high.

The strict regime has enough rows for descriptive summaries, but it may be too narrow for creator and flow stability. The existing all-collected cohort is 3,000 launches. A controlled comparison between strict regime and all-collected launches would tell whether the weak T002/T005 signal is regime-dependent or simply a broad activity artifact.

Recommended scope:

- Do not create new theses yet.
- Build a cohort comparison report across strict 1,500 and all-collected 3,000.
- Compare coverage, FDV-proxy outcome distribution, and T005 baseline-control summaries.
- Keep conclusions descriptive only.

### 3. Entity / Manipulation Enrichment

Expected value: medium, but higher infrastructure cost.

This path is important, but it should follow or run behind holder-state enrichment because direct entity features are harder to validate. T006 shows that intensity ratios alone are not evidence of manipulation. If this lane proceeds, it needs explicit evidence features, not labels inferred from behavior.

Candidate fields:

- improved sniper share
- bundler share
- insider share
- repeated funder patterns
- linked wallet clusters with transparent heuristics
- suspicious circular activity indicators with conservative naming

Recommended scope:

- Start with a small audited fixture workflow.
- Avoid calling anything manipulation unless directly supported by deterministic evidence.
- Use entity features as explanatory diagnostics, not thesis promotion inputs.

## Paths To Park Or Kill

Park for now:

- T004 liquidity persistence using bonding-curve reserve proxy only. It is cleanly measured, but it did not show signal and is not true DEX depth.
- T006 participation-quality ratios. They are well covered, but did not add descriptive information beyond raw activity.
- T003 creator archetype inside the strict regime only. It should be rerun only after broader chronological creator history exists.

Keep as baseline:

- T005 buy/sell flow baseline. It remains useful as a control family because it is fully covered and weakly descriptive, but it should not be treated as an alpha thesis.

Rerun after data upgrade:

- T001 after true holder distribution and top holder share are available.
- T002 after true holder-count and holder-retention snapshots are available.

Kill:

- None yet. The right decision is to park shallow proxy versions, not kill the underlying thesis families.

## Hard Recommendation

Do next:

1. Build bounded true holder-state enrichment for the strict launch-regime cohort.
2. Rerun only T001 and T002 after holder-state coverage is measurable.
3. Keep T005 as a baseline/control comparator.

Do not do next:

- Do not start paper trading.
- Do not run live trading.
- Do not optimize thresholds.
- Do not create entry or exit rules from T002/T005 weak signals.
- Do not promote any thesis from this descriptive pass.
- Do not spend the next sprint deepening participation-quality ratios without better holder/entity state.

External deep research is not recommended yet. The bottleneck is local data quality and missing state fields, not a literature gap. External research becomes useful after holder-state enrichment shows a repeatable descriptive pattern and the team needs to decide which historical mechanisms could explain it.

More infrastructure work is justified only for:

- replay-safe holder-state snapshots,
- holder distribution and top-holder concentration,
- broader cohort comparison,
- carefully audited entity/funder linkage.

Infrastructure work is not justified for:

- new strategy execution,
- paper-trading plumbing,
- threshold search,
- ML ranking,
- more proxy-only flow ratios.

## Current Research Direction

The project should pivot from additional shallow descriptive theses to state enrichment. The first six cycles suggest the current raw lifecycle activity fields are good enough to describe behavior but not enough to explain edge. The next research direction is true holder-state enrichment, followed by a targeted rerun of T001 and T002. Only after that should broader cohort tests or external mechanism research be prioritized.

