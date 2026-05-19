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
python main.py proof-candidates --limit 25
python main.py export-manual-research --limit 25
```

This creates:

```text
data/manual_research/manual_research_packet.csv
data/manual_research/manual_research_packet.json
data/manual_research/manual_evidence_template.csv
```

Open `manual_research_packet.csv` first. It tells you which rows are highest priority and gives links to Solscan, Solana Explorer, and Dexscreener.

## How To Research A Row

1. Start with row 1 in `manual_research_packet.csv`.
2. Open the Solscan token link.
3. Use the Solscan Activities/Transactions filters to inspect historical activity around the decision timestamp.
4. Open Solana Explorer for the mint account if Solscan is not enough.
5. Open Dexscreener only as supporting context, not as proof unless the historical timestamp is clear.
6. If you can verify supply or market cap at or before the decision time, enter it into `manual_evidence_template.csv`.
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

`verified_supply` is required only for `A_FULL_REPLAY_SAFE`.

`verified_market_cap` may be used for `B_STRONG_PARTIAL` or `C_SUGGESTIVE` when you have historical chart evidence but no supply proof. Those rows are retained as research evidence but do not unblock proof readiness.

`verified_supply` is the key field needed to recompute market cap from existing decision-time price.

## How To Import Evidence

After filling the template, run:

```bash
python main.py import-manual-evidence data/manual_research/manual_evidence_template.csv
python main.py proof-readiness
```

The importer rejects rows with:

- Missing candidate ID.
- Missing mint.
- Tier A evidence with missing supply.
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

Only `A_FULL_REPLAY_SAFE` rows create manual supply evidence that can be treated as replay-safe. Lower tiers stay available for review but do not validate wallet trust.

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
