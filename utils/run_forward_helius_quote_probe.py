#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.env_loader import load_env  # noqa: E402
from utils.run_forward_wallet_activity import build_forward_rpc_client  # noqa: E402
from wallets.forward_helius_quote_probe import build_forward_helius_quote_probe  # noqa: E402


DEFAULT_REJECTED = ROOT / "data" / "reports" / "forward_testing" / "forward_entry_context_resolver_rejected.jsonl"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reports" / "forward_testing" / "helius_quote_probe"

FIELDS = [
    "wallet_address",
    "event_id",
    "token_mint",
    "transaction_signature",
    "signal_time",
    "source_block_reason",
    "status",
    "transaction_found",
    "parsed_token_delta_rows",
    "matching_token_delta_found",
    "quote_mint",
    "quote_amount_delta",
    "execution_price_quote",
    "execution_price_source",
    "native_sol_raw_lamports_delta",
    "native_sol_adjusted_lamports_delta",
    "native_sol_fee_lamports",
    "repair_allowed",
    "promotion_allowed",
    "can_mutate_wallet_trust",
    "wallet_list_mutation_allowed",
    "notes",
]


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def relative_path(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def write_json(path: Path | str, payload: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path | str, rows: list[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def write_forward_helius_quote_probe(
    *,
    rejected_records_path: Path | str = DEFAULT_REJECTED,
    output_dir: Path | str = DEFAULT_OUTPUT_DIR,
    rpc: Any | None = None,
    wallet: str | None = None,
    max_rows: int = 5,
    execute: bool = False,
    paid_rpc_allowed: bool = False,
    run_id: str | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    run_id = run_id or default_run_id()
    if execute and not paid_rpc_allowed:
        raise ValueError("Helius quote probe execute mode requires --allow-paid-rpc.")
    if execute and rpc is None:
        load_env()
        rpc = build_forward_rpc_client(allow_paid_rpc=paid_rpc_allowed, timeout=15)
    report = build_forward_helius_quote_probe(
        rejected_records=read_jsonl(rejected_records_path),
        rpc=rpc,
        wallet=wallet,
        max_rows=max_rows,
        execute=execute,
        paid_rpc_allowed=paid_rpc_allowed,
        run_id=run_id,
        generated_at=generated_at,
    )
    report["input_paths"] = {
        "forward_entry_context_resolver_rejected": relative_path(rejected_records_path),
    }
    out = Path(output_dir)
    json_path = out / f"forward_helius_quote_probe_{run_id}.json"
    csv_path = out / f"forward_helius_quote_probe_{run_id}.csv"
    report["output_paths"] = {
        "json": relative_path(json_path),
        "csv": relative_path(csv_path),
    }
    write_json(json_path, report)
    write_csv(csv_path, report.get("rows") or [])
    write_json(out / "forward_helius_quote_probe.json", report)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a tiny review-only Helius quote recovery probe.")
    parser.add_argument("--rejected-records", type=Path, default=DEFAULT_REJECTED)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--wallet", default=None)
    parser.add_argument("--max-rows", type=int, default=5)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--execute", action="store_true", help="Fetch selected transactions from Helius.")
    parser.add_argument(
        "--allow-paid-rpc",
        action="store_true",
        help="Required with --execute so paid-RPC usage is explicit.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = write_forward_helius_quote_probe(
        rejected_records_path=args.rejected_records,
        output_dir=args.output_dir,
        wallet=args.wallet,
        max_rows=args.max_rows,
        execute=args.execute,
        paid_rpc_allowed=args.allow_paid_rpc,
        run_id=args.run_id,
    )
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    print(json.dumps(report["output_paths"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
