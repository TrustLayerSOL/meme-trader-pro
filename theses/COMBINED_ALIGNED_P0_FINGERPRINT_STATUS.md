# Combined Aligned P0 Fingerprint Status

## Why This Exists
Combines original, balanced second-pass, and leftover aligned P0 structural enrichment into one descriptive fingerprint dataset.

## Coverage
- Unique launches: `712`
- All-three P0 launches: `539`
- Balanced sample rows: `462`
- Leftover sample rows: `250`
- Duplicate rows resolved: `113`

## Findings
- Strongest visible features: `['active_wallets_at_20k']`
- Strongest hidden structural features: `['launches_sharing_funder', 'creators_sharing_funder', 'shared_funding_proxy', 'early_buyer_with_prior_runner_count', 'time_linked_funding_proxy']`
- Candidate fingerprints: `['High FDV efficiency + repeated runner buyers', 'High FDV efficiency + shared funder/time-linked funding', 'Low event density + stable top-holder structure', 'Fast expansion + low early-buyer failure history', 'High runner-wallet quality + low creator distribution']`

## Limitations
- `['true_market_cap_claims_remain_blocked', 'fdv_proxy_only', 'top_holder_addresses_unavailable', 'leftover_sample_is_date_concentrated', 'descriptive_only_no_validation_or_trading_claim']`

## Next Recommendation
A. Full runner fingerprint report is ready for formal thesis selection.
