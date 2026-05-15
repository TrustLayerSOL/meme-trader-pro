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
from wallets.wallet_cycle_report import build_wallet_cycle_report


def write_wallet_cycle_report(
    *,
    out_path: Path | str = ROOT / "data" / "wallet_cycle_report.json",
    tracked_wallets: Any | None = None,
    paper_watch_wallets: Any | None = None,
    bad_wallets: Any | None = None,
    candidate_audit: Any | None = None,
    wallet_replay_scorecard: Any | None = None,
    review_decisions: Any | None = None,
    wallet_list_update_audit: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    report = build_wallet_cycle_report(
        tracked_wallets=tracked_wallets if tracked_wallets is not None else read_json(ROOT / "data" / "tracked_wallets.json", []),
        paper_watch_wallets=paper_watch_wallets if paper_watch_wallets is not None else read_json(ROOT / "data" / "paper_watch_wallets.json", {"wallets": []}),
        bad_wallets=bad_wallets if bad_wallets is not None else read_json(ROOT / "data" / "bad_wallets.json", []),
        candidate_audit=candidate_audit if candidate_audit is not None else read_json(ROOT / "data" / "wallet_candidate_audit.json", {}),
        wallet_replay_scorecard=wallet_replay_scorecard if wallet_replay_scorecard is not None else read_json(ROOT / "data" / "wallet_replay_scorecard.json", {}),
        review_decisions=review_decisions if review_decisions is not None else read_json(ROOT / "data" / "wallet_review_decisions.json", {"decisions": []}),
        wallet_list_update_audit=wallet_list_update_audit if wallet_list_update_audit is not None else read_json(ROOT / "data" / "wallet_list_update_audit.json", {"updates": []}),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    out = ROOT / "data" / "wallet_cycle_report.json"
    report = write_wallet_cycle_report(out_path=out)
    counts = report["counts"]
    queue = report["review_queue"]
    print(
        "wrote {} tracked={} active_paper_watch={} blocked={} pending_promotion={} pending_demotion={}".format(
            out.relative_to(ROOT),
            counts["tracked_wallets"],
            counts["active_paper_watch_wallets"],
            counts["blocked_paper_watch_wallets"],
            queue["promotion_review"],
            queue["demotion_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
