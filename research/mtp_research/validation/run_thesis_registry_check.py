"""CLI for checking the thesis registry."""

from __future__ import annotations

import argparse
from collections import Counter

from research.mtp_research.validation.thesis_registry import REQUIRED_FIELDS, ThesisRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description="Check MemeTraderPro thesis registry.")
    parser.add_argument("--theses-dir", default="theses")
    args = parser.parse_args()

    registry = ThesisRegistry(args.theses_dir)
    theses = registry.load_theses()
    ids = [thesis.thesis_id for thesis in theses]
    duplicate_ids = sorted([thesis_id for thesis_id, count in Counter(ids).items() if count > 1])
    missing_required = [
        thesis.thesis_id
        for thesis in theses
        if _missing_required_fields(thesis)
    ]

    print(f"thesis_count={len(theses)}")
    print(f"status_counts={dict(sorted(Counter(thesis.status for thesis in theses).items()))}")
    print(f"strategy_family_counts={dict(sorted(Counter(thesis.strategy_family for thesis in theses).items()))}")
    for thesis in theses:
        print(f"{thesis.thesis_id}: {thesis.name}")

    if not theses:
        print("error=no_thesis_files_found")
        return 1
    if duplicate_ids:
        print(f"error=duplicate_thesis_id:{duplicate_ids}")
        return 1
    if missing_required:
        print(f"error=missing_required_fields:{missing_required}")
        return 1
    return 0


def _missing_required_fields(thesis) -> bool:
    frontmatter = thesis.metadata_json.get("frontmatter", {})
    return bool(REQUIRED_FIELDS - set(frontmatter))


if __name__ == "__main__":
    raise SystemExit(main())
