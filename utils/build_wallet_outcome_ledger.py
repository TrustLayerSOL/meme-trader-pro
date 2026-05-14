from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.rejection_logger import DEFAULT_REJECT_PATH
from research.signal_schema import build_record_from_rejection, build_record_from_trade
from wallets.wallet_outcome_ledger import build_wallet_outcome_ledger


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path, limit: int = 5_000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
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


def paper_trade_rows(paper_state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for bucket in ("open_trades", "closed_trades", "failed_trades"):
        for trade in paper_state.get(bucket) or []:
            if isinstance(trade, dict):
                row = dict(trade)
                row.setdefault("_bucket", bucket)
                rows.append(row)
    return rows


def build_records(
    *,
    paper_path: Path | None = None,
    rejection_path: Path | None = None,
    rejection_limit: int = 5_000,
) -> list[dict[str, Any]]:
    paper_path = Path(paper_path or ROOT / "data" / "paper_trades.json")
    rejection_path = Path(rejection_path or ROOT / DEFAULT_REJECT_PATH)
    records = []

    for trade in paper_trade_rows(read_json(paper_path, {})):
        try:
            records.append(build_record_from_trade(trade))
        except Exception:
            continue

    for rejection in read_jsonl(rejection_path, limit=rejection_limit):
        try:
            records.append(build_record_from_rejection(rejection))
        except Exception:
            continue

    return records


def main() -> int:
    records = build_records()
    report = build_wallet_outcome_ledger(records)
    out = ROOT / "data" / "wallet_outcome_ledger.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(
        "wrote {} wallets={} records={}".format(
            out.relative_to(ROOT),
            report["counts"]["wallets"],
            report["counts"]["records"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

