"""CLI for the structural enrichment master plan."""

from __future__ import annotations

import argparse

from research.mtp_research.validation.structural_enrichment_master_plan import (
    DEFAULT_OUTPUT_DIR,
    DEFAULT_STATUS_PATH,
    build_structural_enrichment_master_plan,
)


def main() -> int:
    args = parse_args()
    report, paths = build_structural_enrichment_master_plan(
        output_dir=args.output_dir,
        status_path=args.status_path,
    )
    families = {row["data_family"] for row in report["inventory"]}
    p0 = [row["data_family"] for row in report["priority_rank"] if row["priority"] == "P0"]
    p1 = [row["data_family"] for row in report["priority_rank"] if row["priority"] == "P1"]
    helius = [row["plan_id"] for row in report["helius_budget_plan"] if row["plan_id"] != "full_structural_enrichment_ceiling"]
    print(f"report_id={report['report_id']}")
    print(f"readiness_classification={report['readiness_classification']}")
    print(f"data_families_inventoried={len(families)}")
    print(f"p0_enrichments={p0}")
    print(f"p1_enrichments={p1}")
    print(f"helius_fetches_recommended={helius}")
    print(f"estimated_pilot_helius_credits={report['recommended_campaign']['estimated_helius_credits']}")
    print(f"recommended_next_sprint={report['recommended_campaign']['exact_next_implementation_sprint']}")
    for key, path in paths.items():
        print(f"{key}={path}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run structural enrichment master plan.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--status-path", default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
