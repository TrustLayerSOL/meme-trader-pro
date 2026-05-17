#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.live_signal_foundation import build_live_signal_foundation_report


DEFAULT_SIGNAL_CONTEXT = ROOT / "data" / "reports" / "signal_context" / "signal_context_layer_report.json"
DEFAULT_REPLAY_SUMMARY = ROOT / "data" / "historical_replay" / "summary.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "live_signal" / "live_signal_foundation_report.json"


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


def write_live_signal_foundation_report(
    *,
    signal_context_path: Path = DEFAULT_SIGNAL_CONTEXT,
    historical_replay_summary_path: Path = DEFAULT_REPLAY_SUMMARY,
    output_path: Path = DEFAULT_OUTPUT,
    generated_at: float | None = None,
) -> dict[str, Any]:
    report = build_live_signal_foundation_report(
        signal_context_layer=read_json(signal_context_path, {}),
        historical_replay_summary=read_json(historical_replay_summary_path, {}),
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "signal_context_layer": rel(signal_context_path),
        "historical_replay_summary": rel(historical_replay_summary_path),
    }
    report["output_paths"] = {"report": rel(output_path)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_live_signal_foundation_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

