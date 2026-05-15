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
from wallets.wallet_candidate_evidence_plan import build_wallet_candidate_evidence_plan


def write_wallet_candidate_evidence_plan(
    *,
    out_path: Path | str = ROOT / "data" / "wallet_candidate_evidence_plan.json",
    candidate_quality_review: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    plan = build_wallet_candidate_evidence_plan(
        candidate_quality_review=candidate_quality_review if candidate_quality_review is not None else read_json(ROOT / "data" / "wallet_candidate_quality_review.json", {"shortlist": []}),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
    return plan


def main() -> int:
    out = ROOT / "data" / "wallet_candidate_evidence_plan.json"
    plan = write_wallet_candidate_evidence_plan(out_path=out)
    summary = plan["summary"]
    print(
        "wrote {} candidates={} ready={} needs_replay={} needs_outcome={} risk={}".format(
            out.relative_to(ROOT),
            summary["total_candidates"],
            summary["ready_for_review"],
            summary["needs_replay_coverage"],
            summary["needs_outcome_coverage"],
            summary["risk_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
