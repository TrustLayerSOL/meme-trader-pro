#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.json_store import read_json
from wallets.wallet_candidate_quality_review import build_wallet_candidate_quality_review


def write_wallet_candidate_quality_review(
    *,
    out_path: Path | str = ROOT / "data" / "wallet_candidate_quality_review.json",
    candidate_quality_report: Any | None = None,
    wallet_replay_scorecard: Any | None = None,
    wallet_outcome_ledger: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    report = build_wallet_candidate_quality_review(
        candidate_quality_report=candidate_quality_report if candidate_quality_report is not None else read_json(ROOT / "data" / "wallet_candidate_quality_report.json", {"ranked_candidates": []}),
        wallet_replay_scorecard=wallet_replay_scorecard if wallet_replay_scorecard is not None else read_json(ROOT / "data" / "wallet_replay_scorecard.json", {}),
        wallet_outcome_ledger=wallet_outcome_ledger if wallet_outcome_ledger is not None else read_json(ROOT / "data" / "wallet_outcome_ledger.json", {}),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    out = ROOT / "data" / "wallet_candidate_quality_review.json"
    report = write_wallet_candidate_quality_review(out_path=out)
    summary = report["summary"]
    print(
        "wrote {} reviewed={} promotion_ready={} observe_more={} risk_review={} reject={}".format(
            out.relative_to(ROOT),
            summary["total_reviewed"],
            summary["promotion_review_ready"],
            summary["observe_more"],
            summary["risk_review"],
            summary["reject_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
