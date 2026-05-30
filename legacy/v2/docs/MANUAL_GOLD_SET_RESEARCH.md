# Manual Gold Set Research

MemeTraderPro is currently blocked by missing decision-time supply and market-cap proof for many otherwise useful wallet evidence rows. Paid archival account-state providers would solve part of this, but the current workflow must work without paid data. The Manual Gold Set workflow gives the operator a small, high-value research queue that can be checked with free public sources, then imported without weakening replay safety.

This workflow is for evidence recovery only. It does not unlock live trading, promote wallets, demote wallets, or change execution behavior.

## What Evidence Is Needed

Most blocked rows already have decision-time price and liquidity. They are blocked because the system cannot prove the token supply, and therefore cannot prove market cap, at or before the signal decision time.

Useful evidence includes:

- Token supply at or before the decision slot or decision timestamp.
- Market cap at or before the decision slot or decision timestamp.
- A public source URL showing the evidence.
- Notes explaining why the evidence is decision-time safe.
- A screenshot path if you saved one locally.

Do not use current supply or current market cap as historical proof.

Current supply is only useful after a separate stability proof shows that mint-account history covers the decision slot and post-decision window with no mint/burn changes. If that proof is missing, mark the row as partial or insufficient instead of Tier A.

The no-paid stability workflow is:

```bash
python3 utils/collect_post_decision_supply_transactions.py --execute --max-targets 5 --max-pages-per-mint 2 --max-transactions-per-mint 500
python3 utils/build_post_decision_supply_coverage.py
python3 utils/build_supply_stability_evidence.py
```

Only after those reports prove coverage should current supply be allowed into replay-safe evidence. Manual screenshots or current token pages do not replace this proof.

## Confidence Tiers

Use `A_FULL_REPLAY_SAFE` only when the evidence clearly applies at or before the decision slot or decision timestamp. This is the only tier allowed to unblock proof rows.

Use `B_STRONG_PARTIAL` when the evidence is strong but not fully decision-time safe. Example: a public page strongly suggests the value was stable around that time, but does not prove the exact slot or timestamp.

Use `C_SUGGESTIVE` when the evidence may help research but should not be trusted for scoring. Example: a later chart or token page supports the idea but does not prove the decision-time value.

Use `D_INSUFFICIENT` when the row could not be verified or the evidence is too weak.

## What Does Not Count

These should not be marked Tier A:

- Current supply from a live token page.
- Current market cap from Dexscreener.
- A chart view without a clear historical timestamp.
- A screenshot without a source URL.
- A guessed supply based on common meme-token defaults.
- A market cap computed from current data.
- Evidence that happens after the decision time.

## How To Create The Research Packet

Run:

```bash
python main.py proof-candidate-groups --limit 25
python main.py export-manual-research-groups --limit 25
python main.py export-manual-entry-sheet --limit 25
python main.py proof-candidates --limit 25
python main.py export-manual-research --limit 25
```

Use the grouped commands first. They collapse repeated rows with the same mint and exact decision timestamp so one verified Tier A historical market-cap check can cover the matching group safely. The HTML entry sheet is the simplest operator surface when using Dexscreener as `B_STRONG_PARTIAL` manual evidence. The ungrouped packet is still useful when you need to inspect a specific wallet/signature row.

This creates:

```text
data/manual_research/manual_research_group_packet.csv
data/manual_research/manual_research_group_packet.json
data/manual_research/manual_group_evidence_template.csv
data/manual_research/manual_market_cap_entry.html
data/manual_research/manual_research_packet.csv
data/manual_research/manual_research_packet.json
data/manual_research/manual_evidence_template.csv
```

Open `manual_research_group_packet.csv` first. It tells you which exact mint/time groups are highest priority and gives links to Solscan, Solana Explorer, and Dexscreener. Fill `manual_group_evidence_template.csv` when a grouped check is valid.

## Simple Dexscreener Entry Sheet

If the full CSV is too noisy, open:

```text
data/manual_research/manual_market_cap_entry.html
```

This page shows only:

- one Dexscreener link for each token
- one UTC one-minute decision bucket underneath it
- one blank market-cap input per token/minute bucket

Type raw market-cap dollars only. For example, `104.80K` becomes `104800`. The page saves typed values in the browser and its `Export CSV` button downloads `manual_market_cap_evidence_filled.csv`. If multiple exact candidate rows fall inside the same token/minute bucket, the export expands that one input into the matching importer rows automatically. The displayed time buckets are UTC, so keep Dexscreener/other sources aligned to UTC when reviewing. Import that downloaded file with:

```bash
python main.py import-manual-evidence path/to/manual_market_cap_evidence_filled.csv
```

The generated CSV uses `B_STRONG_PARTIAL` by default because Dexscreener chart evidence is manual public chart evidence, not archival account-state proof.

## How To Research A Row

1. Start with row 1 in `manual_research_group_packet.csv`.
2. Open the Solscan token link.
3. Use the Solscan Activities/Transactions filters to inspect historical activity around the decision timestamp.
4. Open Solana Explorer for the mint account if Solscan is not enough.
5. Open Dexscreener only as supporting context, not as proof unless the historical timestamp is clear.
6. If you can verify supply or market cap at or before the decision time, enter it into `manual_group_evidence_template.csv`.
7. Add the source URL and notes explaining what you verified.
8. If you are unsure, use `C_SUGGESTIVE` or `D_INSUFFICIENT`.

## Solscan Historical Search Path

Solscan now exposes full historical activity search across raw and decoded transaction surfaces. Use it as a low-cost evidence recovery source.

Useful Solscan checks:

- Open the candidate token page.
- Use the `Activities`, `Transactions`, or `Transfers` tab.
- Filter by time around the candidate decision timestamp.
- Filter by token involved, program involved, action, or transfer value when available.
- Export CSV when Solscan provides a clean historical slice.

Solscan historical rows are useful for confirming:

- swaps near the decision time
- USD-valued activity near the decision time
- programs used by the token around the signal
- whether activity was normal, thin, or suspicious

The importer supports Solscan's current DeFi activity export format, including `Human Time`,
`Block Time`, `Amount1`/`Amount2`, `TokenDecimals1`/`TokenDecimals2`, `Token1`/`Token2`,
`Value`, `From`, and `Programs`.

Solscan historical rows do not automatically prove:

- exact token supply at the decision slot
- exact replay-safe market cap
- that a wallet should be promoted

To import a Solscan CSV as partial evidence, run:

```bash
python main.py import-solscan-evidence path/to/solscan_export.csv \
  --candidate-id manual_example_candidate_id \
  --source-url "https://solscan.io/token/MINT#activities"
```

This stores Solscan evidence separately:

```text
data/manual_research/solscan_historical_evidence_imported.jsonl
data/manual_research/solscan_historical_evidence_rejected.csv
data/manual_research/solscan_historical_evidence_import_report.json
```

Imported Solscan historical activity evidence is treated as `B_STRONG_PARTIAL` when it has usable USD value, otherwise `C_SUGGESTIVE`. It does not increase proof readiness by itself.

## How To Fill The Template

Use:

```text
candidate_id
mint
decision_slot
decision_timestamp
verified_supply
verified_market_cap
evidence_source
evidence_url
screenshot_path
confidence_tier
notes
```

Required fields:

- `candidate_id`
- `mint`
- `decision_slot`
- `decision_timestamp`
- `evidence_source`
- `confidence_tier`
- `notes`

For `A_FULL_REPLAY_SAFE`, provide either `verified_supply` or `verified_market_cap`.

`verified_market_cap` may be Tier A when the source clearly shows market cap at or before the decision timestamp, such as a historical chart crosshair on the exact candidate time. If the timestamp is unclear, use `B_STRONG_PARTIAL` or `C_SUGGESTIVE`; those rows are retained as research evidence but do not unblock proof readiness.

When multiple rows share the same mint and decision timestamp, one Tier A historical market-cap entry can cover the matching group. This is only allowed when the timestamp matches exactly; do not reuse evidence across different times.

For the focused archival supply workflow, use `raw_supply_base_units`, not display supply. Display supply is the human-readable supply shown by explorers. Raw base-unit supply is display supply multiplied by `10 ** decimals`. Tier A supply evidence should only use raw base units or a provider response that exposes the raw mint-account supply directly.

## How To Import Evidence

After filling the template, run:

```bash
python main.py import-manual-evidence data/manual_research/manual_group_evidence_template.csv
python main.py proof-readiness
```

If you used the ungrouped packet instead, import `data/manual_research/manual_evidence_template.csv`.

The importer rejects rows with:

- Missing candidate ID.
- Missing mint.
- Tier A evidence with neither verified supply nor verified market cap.
- Supply less than or equal to zero when supply is provided.
- Impossible market cap values.
- Missing source.
- Missing notes.
- Invalid confidence tier.
- Candidate mismatch.
- Decision slot or timestamp mismatch.

It also preserves stronger evidence. If a candidate already has Tier A evidence, a weaker Tier B/C/D row will not overwrite it.

## How Manual Evidence Affects Proof Readiness

Manual evidence is stored separately from provider evidence:

```text
data/manual_research/manual_evidence_imported.jsonl
data/manual_research/manual_supply_evidence_records.jsonl
```

`A_FULL_REPLAY_SAFE` rows with verified supply create manual supply evidence. `A_FULL_REPLAY_SAFE` rows with verified historical market cap can make matching price/liquidity rows score-ready without inventing supply. Lower tiers stay available for review but do not validate wallet trust.

Manual market-cap evidence is matched first by exact wallet/mint/transaction. If the exact row differs, it may also match rows with the same mint and exact decision timestamp so repeated observations do not require duplicate browser work.

Run:

```bash
python main.py proof-readiness
```

Review:

- manually verified Tier A rows
- Tier B/C/D rows
- remaining blocked rows
- wallet score readiness
- proof readiness
- manual-adjusted proof readiness

## Safety Rule

When uncertain, do not guess. Use `C_SUGGESTIVE` or `D_INSUFFICIENT`. This project needs bounded truth more than optimistic scoring.
