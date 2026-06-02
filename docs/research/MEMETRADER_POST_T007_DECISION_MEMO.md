# MemeTraderPro Post-T007 Decision Memo

## Executive Decision

Recommended next path: **B) build funding-link / fee-payer / source-wallet feasibility**.

The first seven descriptive thesis cycles did not produce a robust research signal from the currently available feature families. The strongest remaining gap is not another outcome test; it is whether the project can recover better launch-entity evidence from funding links, fee payers, source wallets, signers, or related deterministic transaction fields.

Do not expand into new thesis conclusions yet. Do not promote any thesis. Do not build trading rules. The next sprint should be a bounded data-readiness feasibility audit only.

## Dataset State

- Core dataset: strict launch-regime FDV-proxy lifecycle cohort
- Launches: `1,500`
- Lifecycle snapshots: `18,000`
- Outcomes: `1,500`
- Event classification: complete for current lifecycle events
- FDV-proxy outcomes: available
- True market cap: unavailable
- True holder account state: unavailable
- Holder-state v2: observed delta replay only, not full-chain account snapshots
- True DEX depth: unavailable
- Funding-link / fee-payer / source-wallet evidence: currently blocked or not yet proven

## T001-T007 Results Matrix

| Thesis | Name | Current Read | Key Result | Main Caveat | Decision |
|---|---|---:|---|---|---|
| T001 | Early Ownership Concentration | `no_signal` | Original ownership-concentration features did not separate outcomes. | Original top-holder, insider, and bundler fields were unavailable. | Park original version. |
| T001 v2 | Early Ownership Concentration with holder replay | `no_signal` | Replay-derived top-holder and creator-share fields still did not produce a useful descriptive signal. | Holder state is observed delta replay, not confirmed full-chain account state. | Park until richer entity/funding data exists. |
| T002 | Holder Growth Tempo | `weak_signal` | Participation-growth proxies showed weak descriptive structure. | Original version lacked true holder-count growth. | Superseded by v2 and robustness review. |
| T002 v2 | Holder Growth Tempo with holder replay | `weak_signal` | Replay-derived holder growth still showed weak structure. | Holder state is replay-derived and FDV is proxy-only. | Failed robustness; do not use as signal. |
| T002 v2 robustness | Chronological robustness review | `no_robust_signal` | The weak T002 v2 read failed chronological and outlier-sensitivity checks. | No thesis promotion or validation design was run. | Park T002 until better data exists. |
| T003 | Creator Archetype History | `no_signal` | Creator/deployer history inside the strict cohort did not separate outcomes. | History was limited to creators visible in this cohort. | Park pending broader or richer creator evidence. |
| T004 | Liquidity Persistence / Depth Proxy | `no_signal` | Bonding-curve balance proxy did not produce useful separation. | Liquidity proxy is not confirmed DEX depth. | Park as diagnostic only. |
| T005 | Buy/Sell Flow Baseline | `weak_signal` | Simple flow had weak descriptive structure. | Baseline/control only; noisy and outlier-sensitive. | Keep as baseline/control, not an edge thesis. |
| T006 | Participation Quality | `no_signal` | Participation-quality ratios did not add useful structure beyond raw flow. | Ratios are not direct evidence of manipulation or coordinated behavior. | Park. |
| T007 | Entity / Coordination Proxy | `no_signal` | High-coverage deterministic entity proxies did not add clear separation beyond T005. | Actor overlap is not entity resolution; funding-link and grouped-entity fields remain blocked. | Park current proxies; investigate blocked entity-source fields. |

## Common Pattern

The useful pattern is negative: current shallow launch-state features are not enough. Ownership concentration, replay-derived holder growth, creator history, liquidity proxy persistence, participation quality, and deterministic actor-overlap proxies all failed to produce a robust descriptive thesis.

The only weak reads were T002/T002 v2 and T005. T002 v2 did not survive chronological robustness. T005 remains a baseline/control, not an actionable research result. T007 had strong coverage across the proxy fields, but still landed as `no_signal`, which means the current proxy definitions likely do not capture the entity relationships that matter.

The current strict-regime dataset is good enough for descriptive data-quality work, but not enough for edge discovery. FDV-proxy outcomes are acceptable for early descriptive comparisons, but true market-cap claims remain blocked. The next bottleneck is missing entity-source evidence, not another thesis cycle.

## Decision Options

### A) Expand strict regime to all 3,000 launches and rerun only T005/T007 as stability checks

This is reasonable later, but it is not the highest-value next step. It would mostly test whether weak or null behavior persists under a larger cohort. Since T007 already had high proxy coverage and no clear signal, simply doubling the cohort is unlikely to fix the missing-field problem.

Use this only after the funding-link / fee-payer / source-wallet audit clarifies whether better entity evidence can be added.

### B) Build funding-link / fee-payer / source-wallet feasibility

This is the recommended path.

The strongest unresolved question is whether the raw Solana transaction evidence can recover deterministic launch-source fields that current proxies miss:

- fee payer
- transaction signer set
- funding/source wallet hints
- creator/deployer funding relationships
- repeated source-wallet patterns
- account-creation funding trails where available
- safe, bounded examples suitable for manual review

This should be a feasibility sprint only. It should not compare to outcomes, run a thesis, validate a strategy, tune thresholds, or claim manipulation. The deliverable should be a coverage and quality audit showing whether these fields are available, deterministic, and stable enough to justify a T007 v2 or a new T008.

### C) Park MemeTraderPro edge search until new data sources exist

Do not park the project yet. The current feature families have been weak, but the most relevant missing data family has not been tested for feasibility. Park only if the funding-link / fee-payer / source-wallet audit is blocked or yields poor coverage.

## Hard Recommendation

Proceed with **B: funding-link / fee-payer / source-wallet feasibility**.

Do not run another thesis cycle next. Do not expand to all 3,000 launches next. Do not treat T005 as more than a baseline/control. Do not rerun T007 until the blocked entity-source fields are either proven available or formally ruled out.

## Feasibility Sprint Scope

Recommended next sprint:

1. Audit raw and normalized transaction fields for fee payer, signer, creator, deployer, and account-funding evidence.
2. Build a bounded field-availability report for the strict 1,500-launch cohort.
3. Produce deterministic examples for manual review.
4. Report coverage by launch and by evidence type.
5. Classify feasibility as one of:
   - `funding_source_ready_for_entity_thesis`
   - `funding_source_partial_needs_review`
   - `funding_source_blocked`

Success criteria:

- High enough coverage to justify T007 v2 or T008.
- Deterministic field definitions.
- No unsupported entity-resolution claims.
- No outcome comparison during feasibility.
- No thesis promotion.

Failure criteria:

- Fee payer or source-wallet evidence is unavailable for most launches.
- Extracted fields are ambiguous without external data.
- Field quality requires unsupported assumptions.
- Manual-review examples do not support deterministic interpretation.

## What To Park

- T001 original and v2 until better holder/entity data exists.
- T002 and T002 v2 after chronological robustness failure.
- T003 until broader or richer creator history exists.
- T004 as a descriptive liquidity-proxy diagnostic only.
- T006 because it did not add structure beyond raw participation measures.
- Current T007 proxy set until funding-link or source-wallet evidence is tested.

## What To Keep

- T005 as a baseline/control only.
- Strict launch-regime cohort as the cleanest current descriptive cohort.
- FDV-proxy outcomes for descriptive research only.
- Holder-state replay as useful but explicitly limited enrichment.
- Entity proxies as coverage scaffolding, not final entity resolution.

## Final Position

MemeTraderPro should not move toward paper trading, strategy generation, or thesis promotion. The current evidence says the first seven descriptive thesis families are not enough.

The next useful research move is to determine whether the missing launch-entity evidence can be recovered. If that audit succeeds, run a new entity-source thesis later. If it fails, then the project should either expand to all 3,000 launches for limited stability checks or park edge search until new data sources exist.
