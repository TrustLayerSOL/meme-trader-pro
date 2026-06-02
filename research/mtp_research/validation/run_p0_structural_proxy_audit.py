"""CLI for combined P0 structural proxy audit."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.p0_structural_proxy_audit import (
    DEFAULT_AXIOM_PARITY_PATH,
    DEFAULT_CREATOR_FUNDER_PATH,
    DEFAULT_EARLY_BUYER_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    DEFAULT_TOP_HOLDER_PATH,
    DEFAULT_UNIVERSE_PATH,
    build_p0_structural_proxy_audit,
)


def main() -> int:
    args = parse_args()
    report, outputs = build_p0_structural_proxy_audit(
        universe_path=args.universe_path,
        early_buyer_path=args.early_buyer_path,
        top_holder_path=args.top_holder_path,
        creator_funder_path=args.creator_funder_path,
        axiom_parity_path=args.axiom_parity_path,
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    coverage = report["launch_coverage"]
    overlap = report["overlap_audit"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"universe_launches={coverage['universe_launches']}")
    print(f"launches_with_any_p0_structural_data={coverage['launches_with_any_p0_structural_data']}")
    print(f"early_buyer_launches={coverage['early_buyer_launches']}")
    print(f"top_holder_launches={coverage['top_holder_launches']}")
    print(f"creator_funder_launches={coverage['creator_funder_launches']}")
    print(f"all_three_layer_launches={coverage['all_three_layer_launches']}")
    print(f"runners_100k_plus_covered_by_all_three={overlap['runners_100k_plus_covered_by_all_three']}")
    print(f"runners_500k_plus_covered_by_all_three={overlap['runners_500k_plus_covered_by_all_three']}")
    print(f"runners_1m_plus_covered_by_all_three={overlap['runners_1m_plus_covered_by_all_three']}")
    print(f"recommended_next_action={report['scaleup_recommendation']['recommended_action']}")
    for key, path in outputs.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build combined P0 structural proxy audit.")
    parser.add_argument("--universe-path", default=DEFAULT_UNIVERSE_PATH)
    parser.add_argument("--early-buyer-path", default=DEFAULT_EARLY_BUYER_PATH)
    parser.add_argument("--top-holder-path", default=DEFAULT_TOP_HOLDER_PATH)
    parser.add_argument("--creator-funder-path", default=DEFAULT_CREATOR_FUNDER_PATH)
    parser.add_argument("--axiom-parity-path", default=DEFAULT_AXIOM_PARITY_PATH)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
