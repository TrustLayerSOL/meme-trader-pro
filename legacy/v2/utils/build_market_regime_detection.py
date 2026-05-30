#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.market_regime_detection import build_market_regime_detection_report


DEFAULT_REPLAY_SUMMARY = ROOT / "data" / "historical_replay" / "summary.json"
DEFAULT_REPLAY_EVENTS = ROOT / "data" / "historical_replay" / "replay_events.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "market_regimes" / "market_regime_detection_report.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
        if limit is not None and len(rows) >= limit:
            break
    return rows


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_market_regime_detection_report(
    *,
    replay_summary_path: Path = DEFAULT_REPLAY_SUMMARY,
    replay_events_path: Path = DEFAULT_REPLAY_EVENTS,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_market_regime_detection_report(
        replay_summary=read_json(replay_summary_path, {}),
        replay_events=read_jsonl(replay_events_path),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "historical_replay_summary": rel(replay_summary_path),
        "historical_replay_events": rel(replay_events_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_market_regime_detection_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

