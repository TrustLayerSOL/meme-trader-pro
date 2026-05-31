"""CLI for local price proxy coverage diagnostics."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.ingestion.normalized_event_store import NormalizedEventStore
from research.mtp_research.pipeline.real_candidate_filter import real_token_mints_from_registry
from research.mtp_research.validation.outcome_label_store import OutcomeLabelStore
from research.mtp_research.validation.price_coverage_analyzer import PriceCoverageAnalyzer
from research.mtp_research.validation.price_coverage_report_writer import (
    write_report_json,
    write_report_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build price proxy coverage report.")
    parser.add_argument("--events-path", default="data/normalized/events.jsonl")
    parser.add_argument("--outcomes-path", default="data/backtests/outcome_labels.jsonl")
    parser.add_argument("--output-dir", default="data/backtests/reports")
    parser.add_argument("--token-mint")
    parser.add_argument("--real-only", action="store_true")
    parser.add_argument("--min-liquidity-usd", type=float)
    args = parser.parse_args()

    events = NormalizedEventStore(args.events_path).load_all()
    labels = OutcomeLabelStore(args.outcomes_path).load_all()
    if args.token_mint:
        events = [event for event in events if event.token_mint == args.token_mint]
        labels = [label for label in labels if label.token_mint == args.token_mint]
    if args.real_only:
        real_mints = real_token_mints_from_registry(min_liquidity_usd=args.min_liquidity_usd)
        events = [event for event in events if event.token_mint in real_mints]
        labels = [label for label in labels if label.token_mint in real_mints]

    report = PriceCoverageAnalyzer().build_report(events, labels)
    output_dir = Path(args.output_dir)
    markdown_path = write_report_markdown(report, output_dir / f"{report.report_id}.md")
    json_path = write_report_json(report, output_dir / f"{report.report_id}.json")

    print(f"event_count={report.event_count}")
    print(f"events_with_price_quote={report.events_with_price_quote}")
    print(f"price_coverage_rate={report.price_coverage_rate}")
    print(f"token_count={report.token_count}")
    print(f"tokens_with_price={report.tokens_with_price}")
    print(f"no_price_label_count={report.no_price_label_count}")
    print(f"likely_no_price_causes={report.likely_no_price_causes}")
    print(f"recommended_next_actions={report.recommended_next_actions}")
    print(f"markdown_path={markdown_path}")
    print(f"json_path={json_path}")
    print("network_calls=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
