"""CLI for short post-run evidence diagnostics."""

from __future__ import annotations

from research.mtp_research.pipeline.evidence_auditor import EvidenceAuditor


def main() -> int:
    report = EvidenceAuditor().build_report()
    print(f"bottleneck_stage={report.bottleneck_stage}")
    print(f"top_warnings={report.top_warnings}")
    print(f"recommended_next_actions={report.recommended_next_actions}")

    if report.bottleneck_stage == "low_value_backfill_targets":
        print("inspect data/backtests/backfill_targets_plan.jsonl")
        print("seed real candidates with pool_address and creator_wallet")
        print("do not scale Helius backfills yet")
    elif report.bottleneck_stage == "no_raw_transactions":
        print("inspect target addresses")
        print("run one direct Helius probe on a known pool/creator address")
    elif report.bottleneck_stage == "parser_coverage":
        print("head -n 1 data/raw/helius_transactions.jsonl")
        print("./trading_env/bin/python -m research.mtp_research.ingestion.run_parse_raw_transactions --limit 10")
    elif report.bottleneck_stage == "outcome_labeling_or_price_proxy":
        print("./trading_env/bin/python -m research.mtp_research.validation.run_build_outcome_labels --max-snapshots 25")
    elif report.bottleneck_stage == "insufficient_test_evidence":
        print("run a slightly larger bounded backfill only after target quality is confirmed")

    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
