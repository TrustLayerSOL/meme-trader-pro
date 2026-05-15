from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_replay_scorecard import build_wallet_replay_scorecard


DEFAULT_REPLAY_EVENTS = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_OUT = ROOT / "data" / "wallet_replay_scorecard.json"


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[-limit:]
    rows = []
    for line in lines:
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


def write_wallet_replay_scorecard(
    events: list[dict[str, Any]],
    *,
    out_path: Path | str = DEFAULT_OUT,
) -> dict[str, Any]:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    report = build_wallet_replay_scorecard(events)
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "out_path": str(out),
        "counts": report["counts"],
    }


def main() -> int:
    result = write_wallet_replay_scorecard(read_jsonl(DEFAULT_REPLAY_EVENTS))
    print(
        "wrote {} wallets={} events={}".format(
            Path(result["out_path"]).relative_to(ROOT),
            result["counts"].get("wallets", 0),
            result["counts"].get("events", 0),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
