#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.json_store import locked_update_json, read_json
from wallets.wallet_replay_review import build_wallet_replay_review, merge_replay_review_decisions


SCORECARD_FILE = ROOT / "data" / "wallet_replay_scorecard.json"
DECISIONS_FILE = ROOT / "data" / "wallet_review_decisions.json"


def sync_replay_wallet_decisions(
    *,
    scorecard_path: Path | str = SCORECARD_FILE,
    decisions_path: Path | str = DECISIONS_FILE,
    limit: int = 50,
    approved_by: str = "wallet_replay_review",
    timestamp: float | None = None,
) -> dict:
    now = time.time() if timestamp is None else float(timestamp)
    scorecard = read_json(scorecard_path, {})
    review = build_wallet_replay_review(scorecard, limit=limit)

    def updater(current):
        return merge_replay_review_decisions(
            current,
            review,
            approved_at=now,
            approved_by=approved_by,
        )

    updated = locked_update_json(decisions_path, {"decisions": []}, updater)
    summary = updated.get("replay_review_summary") if isinstance(updated.get("replay_review_summary"), dict) else {}
    return {
        "mode": "REPLAY_WALLET_DECISION_SYNC",
        "live_execution_locked": True,
        "tracked_wallets_mutated": False,
        "decisions_path": str(Path(decisions_path)),
        "review_summary": review.get("decision_summary", {}),
        "synced_summary": summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync replay-based wallet review recommendations into wallet_review_decisions.json.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum replay-review rows to consider.")
    parser.add_argument("--approved-by", default="wallet_replay_review", help="Decision author label.")
    ns = parser.parse_args(argv)
    print(json.dumps(sync_replay_wallet_decisions(limit=ns.limit, approved_by=ns.approved_by), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
