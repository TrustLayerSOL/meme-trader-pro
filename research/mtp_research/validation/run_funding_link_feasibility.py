"""CLI for bounded funding-link / fee-payer feasibility audit."""

from __future__ import annotations

import argparse

from research.mtp_research.data_paths import data_lake_path
from research.mtp_research.validation.funding_link_feasibility import (
    build_funding_link_feasibility_report,
    write_funding_link_feasibility_outputs,
)


DEFAULT_CANDIDATES_PATH = data_lake_path(
    "data", "normalized", "launch_regime_classified", "launch_regime_candidates.jsonl"
)
DEFAULT_RAW_TRANSACTION_PATHS = [
    data_lake_path("data", "raw", "pumpfun_lifecycle_2h.jsonl"),
    data_lake_path("data", "raw", "helius_transactions.jsonl"),
]
DEFAULT_OUTPUT_DIR = data_lake_path(
    "data", "backtests", "diagnostics", "reports", "funding_link_feasibility"
)


def main() -> int:
    args = parse_args()
    report = build_funding_link_feasibility_report(
        candidates_path=args.candidates_path,
        raw_transaction_paths=args.raw_transaction_paths,
        max_launches=args.max_launches,
    )
    paths = write_funding_link_feasibility_outputs(report, output_dir=args.output_dir)
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"launches_inspected={report['scope']['launches_inspected']}")
    print(f"external_api_calls_used={report['scope']['external_api_calls_used']}")
    print(f"fee_payer_coverage_pct={report['field_coverage']['fee_payer']['coverage_pct']:.2f}")
    print(f"signer_coverage_pct={report['field_coverage']['signer']['coverage_pct']:.2f}")
    print(f"source_wallet_coverage_pct={report['field_coverage']['source_wallet']['coverage_pct']:.2f}")
    print(f"creator_funding_source_coverage_pct={report['field_coverage']['creator_funding_source']['coverage_pct']:.2f}")
    print(f"deterministic_reconstruction_possible={report['offline_reconstruction']['deterministic_reconstruction_possible']}")
    print(f"offline_only_possible={report['offline_reconstruction']['offline_only_possible']}")
    print(f"new_data_source_required={report['offline_reconstruction']['new_data_source_required']}")
    print(f"t008_feasible={report['t008_feasible']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bounded funding-link feasibility audit.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--raw-transaction-paths", nargs="+", default=DEFAULT_RAW_TRANSACTION_PATHS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-launches", type=int, default=100)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
