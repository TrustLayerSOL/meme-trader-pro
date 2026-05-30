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
from wallets.wallet_candidate_backfill_targets import build_wallet_candidate_backfill_targets


DEFAULT_REPLAY_EVENTS = ROOT / "data" / "historical_replay" / "replay_events.jsonl"


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def write_wallet_candidate_backfill_targets(
    *,
    out_path: Path | str = ROOT / "data" / "wallet_candidate_backfill_targets.json",
    replay_events_path: Path | str = DEFAULT_REPLAY_EVENTS,
    candidate_evidence_plan: Any | None = None,
) -> dict[str, Any]:
    out = Path(out_path)
    report = build_wallet_candidate_backfill_targets(
        candidate_evidence_plan=candidate_evidence_plan if candidate_evidence_plan is not None else read_json(ROOT / "data" / "wallet_candidate_evidence_plan.json", {"coverage_queue": []}),
        replay_events=read_jsonl(replay_events_path),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    out = ROOT / "data" / "wallet_candidate_backfill_targets.json"
    report = write_wallet_candidate_backfill_targets(out_path=out)
    summary = report["summary"]
    print(
        "wrote {} targets={} wallet_history={} outcome_backfill={} more_replay={} risk={}".format(
            out.relative_to(ROOT),
            summary["total_targets"],
            summary["needs_wallet_history"],
            summary["needs_outcome_label_backfill"],
            summary["needs_more_replay_events"],
            summary["risk_review"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
