from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_review_summary import build_wallet_candidate_review_summary


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a review-only summary of wallet candidate audit buckets.")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()

    report = build_wallet_candidate_review_summary(
        read_json(ROOT / "data" / "wallet_candidate_audit.json", {}),
        decision_prep=read_json(ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_decision_prep.json", {}),
        limit=args.limit,
    )
    out = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_review_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    summary = report["summary"]
    print(
        "wrote {} actionable={} risk={} insufficient={} resolved={}".format(
            out.relative_to(ROOT),
            summary["actionable_review"],
            summary["risk_review_required"],
            summary["insufficient_evidence"],
            summary["resolved_candidates"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
