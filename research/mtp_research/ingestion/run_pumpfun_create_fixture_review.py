"""CLI for one reviewed Pump.fun create-signature fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from research.mtp_research.ingestion.pumpfun_create_fixture_review import (
    review_known_create_signature,
    write_fixture_review_report,
)


def main() -> int:
    args = parse_args()
    if not args.execute:
        print("execute=False")
        print(f"known_create_signature={args.known_create_signature}")
        print(f"expected_mint={args.expected_mint}")
        print(f"expected_creator={args.expected_creator}")
        print(f"expected_bonding_curve={args.expected_bonding_curve}")
        print("network_calls=0")
        return 0

    result = review_known_create_signature(
        args.known_create_signature,
        expected_mint=args.expected_mint,
        expected_creator=args.expected_creator,
        expected_bonding_curve=args.expected_bonding_curve,
        min_confidence=args.min_confidence,
    )
    output = write_fixture_review_report(result, args.output_path)
    print(f"accepted={result['accepted']}")
    print(f"parser_confidence={result['parser_confidence']}")
    print(f"rejection_reason={result['rejection_reason']}")
    print(f"direct_pumpfun_instruction_count={result['direct_pumpfun_instruction_count']}")
    print(f"rejected_count={result['rejected_count']}")
    print(f"unknown_count={result['unknown_count']}")
    print(f"output_path={output}")
    print(f"network_calls={result['network_calls']}")
    return 0 if result["accepted"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review one known Pump.fun create signature fixture.")
    parser.add_argument("--known-create-signature", required=True)
    parser.add_argument("--expected-mint", required=True)
    parser.add_argument("--expected-creator", required=True)
    parser.add_argument("--expected-bonding-curve", required=True)
    parser.add_argument("--min-confidence", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--output-path", default="data/backtests/diagnostics/reports/pumpfun_create_fixture_review.json")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
