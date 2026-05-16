#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from wallets.wallet_candidate_context_recovery_closeout import build_wallet_candidate_context_recovery_closeout


DEFAULT_RUNNER = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_runner.json"
DEFAULT_OUTPUT = ROOT / "data" / "reports" / "wallet_reviews" / "wallet_candidate_context_recovery_closeout.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_report(
    *,
    runner_path: Path = DEFAULT_RUNNER,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    report = build_wallet_candidate_context_recovery_closeout(
        recovery_runner=read_json(runner_path, {}),
        limit=500,
    )
    report["input_paths"] = {
        "recovery_runner": str(runner_path.relative_to(ROOT)),
    }
    report["output_paths"] = {"report": str(output_path.relative_to(ROOT))}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = write_report()
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
