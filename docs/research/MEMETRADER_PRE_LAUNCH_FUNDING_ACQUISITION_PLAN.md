# MemeTraderPro Pre-Launch Funding Acquisition Plan

## Executive Decision

Readiness classification: `pre_launch_funding_pilot_ready`.

Recommendation: run a **dry-run-only implementation first**, then a capped 50-creator pilot if the dry-run confirms request counts and the Helius dashboard confirms the current credit multiplier for the selected endpoints.

This is a planning and data-readiness sprint only. It is not a thesis cycle, backtest, validation run, strategy test, optimization pass, or trading workflow.

## Current Feasibility State

The funding-link feasibility audit at commit `7315d0b` found:

- Launches inspected: `100`
- External API calls used: `0`
- Fee payer coverage: `100%`
- Signer coverage: `100%`
- At-launch transfer source coverage: `100%`
- Creator funding source coverage: `0%`
- Creator prior funding wallet coverage: `0%`
- Readiness: `funding_link_partial_needs_data`
- T008 feasible now: `false`

Interpretation: existing local data can reconstruct at-launch transaction structure, but not the creator's pre-launch funding history. T008 remains blocked until prior funding evidence is collected or ruled out.

## Terms That Must Stay Separate

Do not collapse these fields without deterministic evidence:

| Term | Meaning | Current Status |
|---|---|---|
| `creator_wallet` | Wallet recorded as creator/deployer in the Pump.fun creation census. | Available. |
| `creation_signature` | Pump.fun launch transaction signature. | Available. |
| `fee_payer` | First account key paying transaction fees in the creation transaction. | Available from local raw creation transaction metadata. |
| `signer` | Account key marked `signer=true` in transaction metadata. | Available from local raw creation transaction metadata. |
| `transfer_source_wallet` | Source wallet inside parsed transfer instructions in the creation transaction. | Derivable locally for at-launch flows. |
| `prior_funding_wallet` | Wallet that funded the creator before the launch. | Not available locally today. |
| `common_funder` | Prior funding wallet reused across multiple creators or launches. | Requires pre-launch funding history. |

## Data Needed For Creator Prior Funding

For each creator wallet and launch time, collect creator-wallet transaction history before launch and identify inbound funding transfers.

Required fields if later implemented:

- `creator`
- `launch_id`
- `launch_time`
- `prior_funding_wallet`
- `prior_funding_signature`
- `prior_funding_time`
- `prior_funding_age_seconds`
- `prior_funding_amount_sol`
- `prior_funding_token`
- `funding_source_confidence`
- `funding_source_missing_reason`
- `common_funder_cluster_id` if deterministic
- `launches_sharing_prior_funder`
- `creator_prior_funder_reuse_count`

Minimum deterministic evidence:

- Creator wallet transaction signatures before launch.
- Hydrated transaction details for candidate inbound transfers.
- Parsed SOL transfer or token transfer where destination is the creator wallet.
- Block time earlier than launch time.
- Source wallet not equal to creator.
- Transfer amount and token type identified.

## Data Sources Considered

### Existing Local Data

Local raw creation and lifecycle transaction data is sufficient for:

- fee payer
- signer set
- at-launch transfer source wallets
- repeated at-launch fee-payer/source-wallet links

Local data is not sufficient for:

- creator prior funding wallet
- common pre-launch funder
- creator pre-launch financing trace

### Helius Standard RPC

Proposed endpoints:

- `getSignaturesForAddress`
- `getTransaction`

Use case:

1. Query signatures for creator wallet.
2. Stop once transaction block time is outside the selected pre-launch lookback window.
3. Hydrate only candidate signatures inside the lookback window.
4. Parse inbound transfers into the creator wallet.

This is the preferred first pilot source because it is familiar, bounded, resumable, and compatible with the existing raw transaction store patterns.

### Helius Enhanced Transactions

Do not use as the first choice.

It may simplify transfer parsing, but previous guardrails avoid expensive enhanced endpoints unless there is a clear reason. If standard RPC parsing fails or is too slow, evaluate Enhanced Transactions separately with a tiny dry-run estimate before any execution.

### Helius Laserstream / Webhooks

Not appropriate for historical pre-launch reconstruction.

Laserstream and webhooks are useful for live or near-real-time streams, but this task needs historical creator funding history. They should not be used for this sprint.

### Dune / Other Historical Indexes

Potentially useful later if RPC cost or runtime becomes impractical.

Do not switch sources until the standard-RPC pilot proves whether historical funding links are extractable and what the observed volume looks like.

## Lookback Windows

Evaluate four windows in dry-run:

| Window | Purpose | Expected Use |
|---|---|---|
| `1h` | Fast sanity check for immediate pre-launch funding. | Good first dry-run, too narrow for final pilot. |
| `6h` | Captures same-session funding while keeping request volume low. | Good conservative pilot if 24h is too expensive. |
| `24h` | Best initial research window for real pilot. | Recommended pilot window. |
| `7d` | Captures delayed staging/funding behavior. | Useful only after 24h quality is proven. |

Recommended pilot window: `24h`.

Reason: `1h` and `6h` may miss staged creator funding. `7d` is likely too noisy and more expensive for the first pilot. `24h` is the best balance between signal opportunity and bounded runtime.

## Request-Equivalent Cost Estimates

These are request-equivalent estimates, not guaranteed Helius credit charges. Before execution, confirm the current Helius dashboard multiplier for `getSignaturesForAddress` and `getTransaction`.

Assumptions:

- Pilot size: `50` creators.
- Signature page size: up to `1000`.
- Hydrate only signatures inside the lookback window.
- Stop paging once signatures are older than the window.
- Cap hydrated transactions per creator.
- Store raw transactions for replay.

### 50-Creator Pilot

| Window | Signature Requests | Transaction Hydrates | Total Request-Equivalent Estimate | Storage Estimate | Runtime Estimate |
|---|---:|---:|---:|---:|---:|
| `1h` | `50` | `250-500` | `300-550` | `25-100 MB` | `5-15 min` |
| `6h` | `50` | `500-1,000` | `550-1,050` | `50-200 MB` | `10-30 min` |
| `24h` | `50-100` | `1,000-2,500` | `1,050-2,600` | `100-500 MB` | `20-75 min` |
| `7d` | `150-300` | `2,500-7,500` | `2,650-7,800` | `250 MB-1.5 GB` | `1-4 hr` |

Recommended 50-creator pilot cap:

- Lookback: `24h`
- Max creators: `50`
- Max signature pages per creator: `2`
- Max hydrated transactions per creator: `50`
- Total hydrate cap: `2,500`
- Request-equivalent ceiling: `3,000`
- Stop if projected request-equivalent cost exceeds `5,000`

### Full Strict-Cohort Scale Estimate

The strict cohort has `1,500` launches. T003 reported `583` creators in the strict cohort, so scale should be estimated two ways:

- Creator-deduplicated scale: `583` creators.
- Worst-case launch-level scale: `1,500` launch-creator pairs.

| Window | Creator-Deduped Estimate, 583 Creators | Worst-Case Estimate, 1,500 Launches |
|---|---:|---:|
| `1h` | `3,500-6,500` requests | `9,000-16,500` requests |
| `6h` | `6,400-12,200` requests | `16,500-31,500` requests |
| `24h` | `12,250-30,300` requests | `31,500-78,000` requests |
| `7d` | `30,900-90,900` requests | `79,500-234,000` requests |

Expected full strict-cohort storage:

- `24h`, creator-deduped: roughly `1-6 GB`
- `24h`, worst case: roughly `3-15 GB`
- `7d`, worst case: could exceed `25 GB`

Do not run full-cohort collection until the 50-creator pilot proves coverage and parser quality.

## Proposed Command Design

Future command:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_pre_launch_funding_plan \
  --creator-limit 50 \
  --lookback-hours 24 \
  --max-signature-pages-per-creator 2 \
  --max-transactions-per-creator 50 \
  --max-total-transactions 2500 \
  --dry-run
```

Future execute command, only after dry-run review:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_pre_launch_funding_collection \
  --creator-limit 50 \
  --lookback-hours 24 \
  --max-signature-pages-per-creator 2 \
  --max-transactions-per-creator 50 \
  --max-total-transactions 2500 \
  --execute
```

The no-argument command must be dry-run only. Any real fetch must require explicit `--execute`.

## Proposed Output Layout

If implemented later, write raw and derived artifacts under the ORICO data lake:

```text
/Volumes/ORICO/MemeTraderPro/data/raw/pre_launch_funding/
  creator_pre_launch_transactions.jsonl

/Volumes/ORICO/MemeTraderPro/data/backtests/funding_link/
  creator_pre_launch_funding_sources.jsonl
  creator_pre_launch_funding_sources.parquet

/Volumes/ORICO/MemeTraderPro/data/backtests/diagnostics/reports/funding_link_feasibility/
  pre_launch_funding_plan.json
  pre_launch_funding_plan.md
  pre_launch_funding_pilot_audit.json
  pre_launch_funding_pilot_audit.md
```

Do not write generated funding data into the repo-local `data/` tree except ignored dry-run summaries if explicitly requested.

## Field Extraction Rules

Candidate prior funding transfer:

- Transaction block time is before launch time.
- Transaction block time is within the selected lookback window.
- Parsed system transfer destination equals creator wallet; source is not creator.
- Or parsed token transfer destination/wallet equals creator wallet; source is not creator.
- Amount is present.
- Token or native SOL classification is present.

Confidence levels:

| Confidence | Rule |
|---|---|
| `high` | Parsed transfer to creator wallet, source wallet present, amount present, block time present, no transaction error. |
| `medium` | Parsed transfer to creator wallet with source and time, but token/amount semantics need review. |
| `low` | Creator appears in transaction but no clean inbound transfer can be identified. |
| `missing` | No prior funding transfer found inside lookback. |

Common funder rule:

- A `common_funder` exists only when the same prior funding wallet funds two or more distinct creators or launch IDs.
- Do not infer entity groups from shared fee payer alone.
- Do not infer manipulation from common funders.
- Report common funder clusters as deterministic linkage candidates only.

## Stop / Go Gates

Proceed to 50-creator pilot only if:

- Estimated request-equivalent cost is below `5,000`.
- Current Helius credit multiplier confirms the pilot fits safely inside allowance.
- Standard RPC can provide historical transaction details for creator wallets.
- Dry-run shows all creator inputs have launch times and creator wallets.
- Collection is capped and resumable.
- Raw transaction preservation is enabled.

Stop immediately if:

- Helius returns provider, auth, or budget errors.
- The dry-run projects more than `5,000` request-equivalent calls for 50 creators.
- More than `20%` of selected creators lack valid launch time or creator wallet.
- Hydrated transactions cannot expose parsed transfer sources/destinations.
- The command cannot resume without duplicate work.

Go to full-cohort planning only if the 50-creator pilot shows:

- At least `60%` of creators have a high- or medium-confidence prior funding result within `24h`, or a clear missing reason.
- Raw transaction preservation is complete.
- Common funder clusters can be generated deterministically.
- Runtime and request counts match dry-run estimates within reasonable tolerance.
- Manual examples confirm fee payer, signer, creator, transfer source, prior funding wallet, and common funder are not being collapsed.

## Risks

- Creator wallets may be funded well before the selected lookback window.
- Creator funding may occur through token transfers, not SOL.
- Funding may route through multiple intermediate wallets.
- Standard RPC transaction payloads may be large and slow to hydrate.
- Very active creator wallets may require more paging than expected.
- Shared fee payer may be creator itself and not useful as a prior-funding source.
- Common funder clusters may be sparse or ambiguous.
- A richer source may be required if pre-launch history is too expensive through standard RPC.

## T008 Feasibility Criteria

T008 becomes feasible only if the pilot can produce:

- `prior_funding_wallet`
- `prior_funding_signature`
- `prior_funding_time`
- `prior_funding_age_seconds`
- `prior_funding_amount_sol` or token equivalent
- `funding_source_confidence`
- `funding_source_missing_reason`
- `launches_sharing_prior_funder`
- `creator_prior_funder_reuse_count`

Minimum readiness label for T008:

- `pre_launch_funding_ready_for_T008`

If the pilot remains partial, do not run T008. Either revise the data source or park the funding-link thesis family.

## Next Recommendation

Build a dry-run planner first.

Recommended next implementation step:

```bash
./trading_env/bin/python -m research.mtp_research.validation.run_pre_launch_funding_plan \
  --creator-limit 50 \
  --lookback-hours 24 \
  --max-signature-pages-per-creator 2 \
  --max-transactions-per-creator 50 \
  --max-total-transactions 2500 \
  --dry-run
```

Expected dry-run output:

- selected creator count
- launches represented
- lookback window
- estimated signature requests
- estimated transaction requests
- estimated request-equivalent total
- estimated storage
- projected runtime
- stop/go classification
- no network calls
- no thesis run

Only after that dry-run report should a real 50-creator pilot be considered.
