from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_collection_plan import build_wallet_candidate_collection_plan


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a review-only evidence collection plan for current wallet candidates.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    report = build_wallet_candidate_collection_plan(
        read_json(ROOT / "data" / "wallet_candidate_audit.json", {}),
        limit=args.limit,
    )
    out = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_collection_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = report["summary"]
    print(
        "wrote {} targets={} outcome_market={} outcome_labels={} risk={}".format(
            out.relative_to(ROOT),
            summary["total_targets"],
            summary["collect_outcomes_and_market_context"],
            summary["collect_outcome_labels"],
            summary["manual_risk_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
