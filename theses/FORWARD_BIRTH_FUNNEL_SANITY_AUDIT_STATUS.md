# Forward Birth Funnel Sanity Audit Status

## Purpose

This audit was created because the forward birth-to-trigger conversion numbers looked high enough to require a provenance, dedupe, freshness, and selection-bias check before continuing scale-up.

## Counts

- Raw funnel numbers: `{'birth_watch_count': 1, 'fdv_followup_count': 1, 'crossed_10k': 1, 'crossed_15k': 1, 'crossed_20k': 1, 'crossed_30k': 0, 'crossed_50k': 0, 'crossed_100k': 0, 'crossed_500k': 0, 'crossed_1m': 0, 'birth_to_fdv_followup_rate': 1.0, 'birth_to_10k_conversion_rate': 1.0, 'birth_to_20k_conversion_rate': 1.0, '10k_to_20k_conversion_rate': 1.0, '20k_to_100k_conversion_rate': 0.0, '20k_to_500k_conversion_rate': 0.0, '20k_to_1m_conversion_rate': 0.0, 'estimated_births_needed_for_300_crossed_10k': 300, 'estimated_births_needed_for_300_crossed_20k': 300}`
- Strict deduped numbers: `{'birth_watch_count': 1, 'fdv_followup_count': 1, 'crossed_10k': 1, 'crossed_15k': 1, 'crossed_20k': 1, 'crossed_30k': 0, 'crossed_50k': 0, 'crossed_100k': 0, 'crossed_500k': 0, 'crossed_1m': 0, 'birth_to_fdv_followup_rate': 1.0, 'birth_to_10k_conversion_rate': 1.0, 'birth_to_20k_conversion_rate': 1.0, '10k_to_20k_conversion_rate': 1.0, '20k_to_100k_conversion_rate': 0.0, '20k_to_500k_conversion_rate': 0.0, '20k_to_1m_conversion_rate': 0.0, 'estimated_births_needed_for_300_crossed_10k': 300, 'estimated_births_needed_for_300_crossed_20k': 300}`
- Observed-followup-only numbers: `{'birth_watch_count': 1, 'fdv_followup_count': 1, 'crossed_10k': 1, 'crossed_15k': 1, 'crossed_20k': 1, 'crossed_30k': 0, 'crossed_50k': 0, 'crossed_100k': 0, 'crossed_500k': 0, 'crossed_1m': 0, 'birth_to_fdv_followup_rate': 1.0, 'birth_to_10k_conversion_rate': 1.0, 'birth_to_20k_conversion_rate': 1.0, '10k_to_20k_conversion_rate': 1.0, '20k_to_100k_conversion_rate': 0.0, '20k_to_500k_conversion_rate': 0.0, '20k_to_1m_conversion_rate': 0.0, 'estimated_births_needed_for_300_crossed_10k': 300, 'estimated_births_needed_for_300_crossed_20k': 300}`
- True/near-birth observed numbers: `{'birth_watch_count': 0, 'fdv_followup_count': 0, 'crossed_10k': 0, 'crossed_15k': 0, 'crossed_20k': 0, 'crossed_30k': 0, 'crossed_50k': 0, 'crossed_100k': 0, 'crossed_500k': 0, 'crossed_1m': 0, 'birth_to_fdv_followup_rate': None, 'birth_to_10k_conversion_rate': None, 'birth_to_20k_conversion_rate': None, '10k_to_20k_conversion_rate': None, '20k_to_100k_conversion_rate': None, '20k_to_500k_conversion_rate': None, '20k_to_1m_conversion_rate': None, 'estimated_births_needed_for_300_crossed_10k': None, 'estimated_births_needed_for_300_crossed_20k': None}`

## Audit Results

- Milestone provenance result: `{'observed_followup_path': 3}`
- Ordering result: `{'same_timestamp_multiple_milestones': 1}`
- Freshness result: `{'unknown_birth_freshness': 1}`
- Follow-up bias result: `{'bias_risk': 'low_bias_risk', 'group_counts': {'births_crossing_10k_plus': 1}}`
- Validity classification: `funnel_needs_freshness_repair`
- Recommendation: `Repair birth freshness or follow-up timing before trusting trigger conversion rates.`
