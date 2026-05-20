# Focused Archival Response Workflow

MemeTraderPro currently has a focused archival handoff for the rows most likely to move proof-readiness. This is for the `349` provider-recommended request rows across `43` token mints where local mint-history pagination reached the decision area but still could not prove complete historical supply.

This workflow is evidence recovery only. It performs no live trading, no provider call unless explicitly run through a separate capture command, no wallet promotion, and no trust mutation.

## Check Current Status

Run:

```bash
python3 main.py provider-response-workflow
```

The command reports:

- how many focused request rows exist,
- how many response chunks are expected,
- which raw response part files are missing,
- whether a combined raw response file exists,
- how many raw responses have been imported,
- current proof-readiness,
- the next safe action.

The report is written to:

```text
data/reports/historical_backfill/provider_response_workflow_report.json
```

## Free / Manual Research Packet

If paid archival responses are not available, export the focused manual supply packet:

```bash
python3 main.py export-focused-supply-research --limit 349
```

This writes:

```text
data/manual_research/focused_manual_supply_research_packet.csv
data/manual_research/focused_manual_supply_research_packet.json
data/manual_research/focused_manual_supply_template.csv
```

Use the packet CSV to research rows with free sources. Fill the template only when you can verify token supply and decimals at or before `max_acceptable_snapshot_slot`.

The focused supply template uses `raw_supply_base_units`, not display supply. For example, a display supply of `1,000,000,000` with `6` decimals must be entered as `1000000000000000` raw base units. Do not paste a Solscan display supply into `raw_supply_base_units` unless you have converted it to base units.

Allowed confidence tiers:

- `A_FULL_REPLAY_SAFE`: source proves historical supply/decimals at or before the slot.
- `B_STRONG_PARTIAL`: useful but not enough to unblock proof.
- `C_SUGGESTIVE`: review note only.
- `D_INSUFFICIENT`: not usable.

Import the filled template with:

```bash
python3 main.py import-focused-supply-evidence data/manual_research/focused_manual_supply_template.csv
```

Only `A_FULL_REPLAY_SAFE` rows emit replay-safe snapshots at:

```text
data/manual_research/focused_manual_supply_snapshots.jsonl
```

Those snapshots are consumed by:

```bash
python3 utils/build_archival_supply_evidence.py
```

Lower-confidence rows remain review evidence and do not move proof-readiness.

Tier A is intentionally strict. The response slot must match the row's `max_acceptable_snapshot_slot`; older snapshots are treated as stale unless they have already gone through the separate mint-history stability proof lane. If you are using a chart screenshot, a current token page, or a source that does not prove exact-slot raw supply, use `B_STRONG_PARTIAL`, `C_SUGGESTIVE`, or `D_INSUFFICIENT`.

## Files You Need

Focused request chunks live under:

```text
data/reports/historical_backfill/raw_provider_responses/
```

The request files are:

```text
provider_recommended_archival_mint_supply_batch_request.part001.json
provider_recommended_archival_mint_supply_batch_request.part002.json
provider_recommended_archival_mint_supply_batch_request.part003.json
provider_recommended_archival_mint_supply_batch_request.part004.json
```

The matching response templates are:

```text
provider_recommended_archival_mint_supply_batch_response_template.part001.json
provider_recommended_archival_mint_supply_batch_response_template.part002.json
provider_recommended_archival_mint_supply_batch_response_template.part003.json
provider_recommended_archival_mint_supply_batch_response_template.part004.json
```

Each response template tells you the exact raw response file to save:

```text
provider_recommended_archival_mint_supply_batch_raw.part001.json
provider_recommended_archival_mint_supply_batch_raw.part002.json
provider_recommended_archival_mint_supply_batch_raw.part003.json
provider_recommended_archival_mint_supply_batch_raw.part004.json
```

## After Response Parts Exist

Only after the part files exist, combine them:

```bash
python3 utils/combine_provider_response_chunks.py
```

Then import only the focused provider-recommended responses:

```bash
python3 utils/import_provider_recommended_archival_mint_supply_snapshots.py
```

Then rebuild the proof chain:

```bash
python3 utils/collect_post_decision_supply_transactions.py --execute --max-targets 5 --max-pages-per-mint 2 --max-transactions-per-mint 500
python3 utils/build_post_decision_supply_coverage.py
python3 utils/build_supply_stability_evidence.py
python3 utils/build_archival_supply_evidence.py
python3 utils/build_score_ready_market_context.py
python3 utils/build_proof_readiness_blocker_reduction.py
python3 utils/export_archival_supply_proof_readiness.py
python3 main.py proof-readiness
```

## Replay-Safety Rules

The importer only accepts provider responses whose response slot is at or before the candidate decision slot. Responses after the decision boundary stay blocked.

Do not paste current supply into these files. Do not use present-day token pages as historical proof. Current supply is only usable if the separate post-decision coverage and supply-stability reports prove no mint/burn changes after the decision slot. Do not manually edit imported evidence rows to make them pass. If the response is missing, too new, malformed, incomplete, or only suggestive, keep it blocked.

## No-Paid Current-Supply Stability Lane

When paid archival responses are not available, the only safe way to reuse current `getTokenSupply` data is to prove that supply could not have changed after the decision slot. The system now has a separate collector for that:

```bash
python3 utils/collect_post_decision_supply_transactions.py --execute --max-targets 5 --max-pages-per-mint 2 --max-transactions-per-mint 500
python3 utils/build_post_decision_supply_coverage.py
python3 utils/build_supply_stability_evidence.py
```

This lane is still strict:

- it refreshes mint-account signatures from the current chain head,
- it only trusts the refresh if the new head pages overlap the existing checkpoint or reach the decision slot,
- it preserves missing post-decision transaction bodies in a separate raw ledger,
- it writes a separate refreshed checkpoint so it does not race long historical mint-history collection,
- bounded runs prioritize the smallest missing-body targets first,
- it does not mark supply stable by itself,
- `build_post_decision_supply_coverage.py` must still prove all post-decision transaction bodies are present and no mint/burn event occurred.

If the collector reports `partial_post_decision_transaction_bodies_collected` or `blocked_incomplete_head_refresh`, keep the rows blocked and run a smaller follow-up batch. Do not raise proof-readiness from this lane until `post_decision_supply_coverage_report.json` emits completeness updates and `supply_stability_evidence_report.json` emits compatible snapshots.

## Current Expected Blocker

If `provider-response-workflow` says `fill_missing_response_parts`, that is normal until real saved response part files exist. Proof-readiness will not move from these rows until those response parts are filled and imported safely.
