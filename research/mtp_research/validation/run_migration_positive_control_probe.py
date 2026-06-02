"""CLI for the Pump.fun migration positive-control probe."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.migration_positive_control_probe import (
    DEFAULT_CANDIDATES_PATH,
    DEFAULT_KNOWN_MINT,
    DEFAULT_KNOWN_SIGNATURE,
    DEFAULT_OUTPUT_DIR,
    build_migration_positive_control_probe,
    write_migration_positive_control_probe_outputs,
)


def main() -> int:
    args = parse_args()
    report = build_migration_positive_control_probe(
        candidates_path=args.candidates_path,
        known_mint=args.known_mint,
        known_signature=args.known_signature,
        window=args.window,
        max_signature_pages_per_strategy=args.max_signature_pages_per_strategy,
        request_ceiling=args.request_ceiling,
        execute=args.execute,
    )
    paths = write_migration_positive_control_probe_outputs(report, output_dir=args.output_dir)
    control = report["positive_control"]
    print(f"report_id={report['report_id']}")
    print(f"classification={report['classification']}")
    print(f"execute={report['execute']}")
    print(f"known_mint={report['known_mint']}")
    print(f"known_signature_found={control['known_signature_found']}")
    print(f"best_strategy={control['best_strategy']}")
    print(f"hydrated_exact_migration={control['hydrated_exact_migration']}")
    print(f"network_calls_used={report['network_calls_used']}")
    print(f"recommended_next_action={report['recommended_next_action']}")
    print(f"json_path={paths['json_path']}")
    print(f"markdown_path={paths['markdown_path']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a bounded migration positive-control probe.")
    parser.add_argument("--candidates-path", default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--known-mint", default=DEFAULT_KNOWN_MINT)
    parser.add_argument("--known-signature", default=DEFAULT_KNOWN_SIGNATURE)
    parser.add_argument("--window", default="24h", choices=["24h", "72h", "7d"])
    parser.add_argument("--max-signature-pages-per-strategy", type=int, default=3)
    parser.add_argument("--request-ceiling", type=int, default=100)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
