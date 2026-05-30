#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.wallet_ecosystem_intelligence import build_wallet_ecosystem_intelligence_report


DEFAULT_REPLAY_SCORECARD = ROOT / "data" / "wallet_replay_scorecard.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_ecosystems" / "wallet_ecosystem_intelligence_report.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return value if isinstance(value, dict) else default


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_wallet_ecosystem_intelligence_report(
    *,
    replay_scorecard_path: Path = DEFAULT_REPLAY_SCORECARD,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_wallet_ecosystem_intelligence_report(
        replay_scorecard=read_json(replay_scorecard_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {"wallet_replay_scorecard": rel(replay_scorecard_path)}
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_wallet_ecosystem_intelligence_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

