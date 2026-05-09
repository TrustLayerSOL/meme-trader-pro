#!/usr/bin/env python3
"""
Build a watch-only candidate wallet list from local scanner history and optional
read-only mint transaction evidence.

This utility never edits tracked_wallets.json and never places trades.
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.env_loader import load_env
from core.json_store import atomic_write_json, read_json
from core.redaction import redact_secrets
from core.rpc_provider import build_helius_rpc_providers
from core.wallet_discovery import (
    CandidateWalletDiscovery,
    extract_owner_deltas,
    normalize_tracked_wallets,
)


SQLITE_DB = ROOT / "data" / "memetrader.db"
TRACKED_WALLETS = ROOT / "data" / "tracked_wallets.json"
WALLET_PERFORMANCE = ROOT / "data" / "wallet_performance.json"
CANDIDATE_WALLETS = ROOT / "data" / "candidate_wallets.json"


class SyncRpcClient:
    def __init__(self, providers=None, timeout=15):
        self.providers = providers or build_helius_rpc_providers()
        self.timeout = timeout
        self.failures = []

    def call(self, method, params):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }).encode("utf-8")

        self.failures = []
        for provider in self.providers:
            request = Request(
                provider.url,
                data=payload,
                headers={"content-type": "application/json"},
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    data = json.loads(body)
                    if "error" in data:
                        self.failures.append({
                            "provider": provider.name,
                            "safe_url": provider.safe_url,
                            "error": redact_secrets(str(data.get("error")))[:240],
                        })
                        continue
                    return data.get("result")
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                self.failures.append({
                    "provider": provider.name,
                    "safe_url": provider.safe_url,
                    "http_status": exc.code,
                    "error": redact_secrets(detail)[:240],
                })
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                self.failures.append({
                    "provider": provider.name,
                    "safe_url": provider.safe_url,
                    "error": redact_secrets(str(exc))[:240],
                })
        return None


def load_local_events(hours, limit, db_path=SQLITE_DB):
    if not Path(db_path).exists():
        return []

    since = time.time() - (hours * 3600)
    rows = []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT time, event_type, wallet, mint, payload_json
            FROM events
            WHERE time >= ?
              AND wallet IS NOT NULL
              AND wallet != ''
              AND mint IS NOT NULL
              AND mint != ''
            ORDER BY time DESC
            LIMIT ?
            """,
            (since, limit),
        ):
            event = dict(row)
            try:
                payload = json.loads(event.pop("payload_json") or "{}")
            except Exception:
                payload = {}
            event["payload"] = payload if isinstance(payload, dict) else {}
            rows.append(event)
    return rows


def load_winner_mints(min_pnl_pct, max_mints, db_path=SQLITE_DB):
    if not Path(db_path).exists():
        return []

    rows = []
    seen = set()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute(
            """
            SELECT mint, pnl, pnl_pct, reason
            FROM trades
            WHERE status = 'closed'
              AND mint IS NOT NULL
              AND mint != ''
              AND (pnl_pct >= ? OR pnl > 0)
            ORDER BY pnl_pct DESC, close_time DESC
            LIMIT ?
            """,
            (min_pnl_pct, max_mints * 3),
        ):
            mint = row["mint"]
            if mint in seen:
                continue
            seen.add(mint)
            rows.append({
                "mint": mint,
                "winner": True,
                "pnl": row["pnl"],
                "pnl_pct": row["pnl_pct"],
                "reason": row["reason"],
            })
            if len(rows) >= max_mints:
                break
    return rows


def load_mint_signatures(rpc, mint, signature_limit):
    result = rpc.call("getSignaturesForAddress", [mint, {"limit": signature_limit}])
    return result if isinstance(result, list) else []


def load_transaction(rpc, signature):
    return rpc.call(
        "getTransaction",
        [
            signature,
            {
                "encoding": "jsonParsed",
                "maxSupportedTransactionVersion": 0,
                "commitment": "confirmed",
            },
        ],
    )


def build_mint_evidence(rpc, mint_rows, signature_limit=40, max_transactions=20, max_buyers=25):
    evidence = []
    rpc_failures = []
    for mint_row in mint_rows:
        mint = mint_row["mint"] if isinstance(mint_row, dict) else str(mint_row)
        signatures = load_mint_signatures(rpc, mint, signature_limit)
        if not signatures:
            rpc_failures.extend(rpc.failures)
            continue

        early_buyers = []
        # getSignaturesForAddress returns newest first, so reverse the limited
        # window to score the earliest transactions we fetched.
        for item in list(reversed(signatures))[:max_transactions]:
            signature = item.get("signature") if isinstance(item, dict) else None
            if not signature:
                continue
            tx = load_transaction(rpc, signature)
            if not isinstance(tx, dict):
                rpc_failures.extend(rpc.failures)
                continue
            for delta in extract_owner_deltas(tx, mint):
                if delta["side"] != "buy":
                    continue
                delta["signature"] = signature
                early_buyers.append(delta)
                if len(early_buyers) >= max_buyers:
                    break
            if len(early_buyers) >= max_buyers:
                break

        evidence.append({
            "mint": mint,
            "winner": bool(mint_row.get("winner", True)) if isinstance(mint_row, dict) else True,
            "trade_pnl_pct": mint_row.get("pnl_pct") if isinstance(mint_row, dict) else None,
            "early_buyers": early_buyers,
            "signatures_checked": min(len(signatures), max_transactions),
        })
    return evidence, rpc_failures


def build_candidate_report(args):
    load_env()
    tracked_wallets = normalize_tracked_wallets(read_json(TRACKED_WALLETS, []))
    performance = read_json(WALLET_PERFORMANCE, {})
    discovery = CandidateWalletDiscovery(tracked_wallets=tracked_wallets, existing_performance=performance)

    local_events = load_local_events(args.local_hours, args.local_limit) if args.local_hours > 0 else []
    mint_rows = []
    if args.from_paper_winners:
        mint_rows.extend(load_winner_mints(args.min_winner_pnl_pct, args.max_winner_mints))
    for mint in args.mint or []:
        mint_rows.append({"mint": mint, "winner": True, "reason": "manual_cli_mint"})

    mint_evidence = []
    rpc_failures = []
    if mint_rows:
        rpc = SyncRpcClient(timeout=args.rpc_timeout)
        mint_evidence, rpc_failures = build_mint_evidence(
            rpc,
            mint_rows,
            signature_limit=args.signature_limit,
            max_transactions=args.max_transactions,
            max_buyers=args.max_buyers_per_mint,
        )

    report = discovery.build_report(local_events=local_events, mint_evidence=mint_evidence)
    report["config"] = {
        "local_hours": args.local_hours,
        "local_limit": args.local_limit,
        "from_paper_winners": args.from_paper_winners,
        "manual_mints": args.mint or [],
        "min_winner_pnl_pct": args.min_winner_pnl_pct,
        "max_winner_mints": args.max_winner_mints,
        "signature_limit": args.signature_limit,
        "max_transactions": args.max_transactions,
        "max_buyers_per_mint": args.max_buyers_per_mint,
    }
    report["source_counts"] = {
        "tracked_wallets": len(tracked_wallets),
        "local_events": len(local_events),
        "winner_mints": len(mint_rows),
        "mint_evidence": len(mint_evidence),
        "rpc_failures": len(rpc_failures),
    }
    if rpc_failures:
        report["rpc_failures"] = rpc_failures[:12]
    return report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Discover watch-only candidate wallets.")
    parser.add_argument("--local-hours", type=float, default=24, help="Hours of local scanner events to mine.")
    parser.add_argument("--local-limit", type=int, default=20000, help="Maximum local events to read.")
    parser.add_argument("--from-paper-winners", action="store_true", help="Mine early buyers from winning paper trades.")
    parser.add_argument("--min-winner-pnl-pct", type=float, default=25, help="Minimum paper PnL percent for winner mining.")
    parser.add_argument("--max-winner-mints", type=int, default=5, help="Maximum winning mints to inspect.")
    parser.add_argument("--mint", action="append", help="Mint to inspect for early buyer evidence. Repeatable.")
    parser.add_argument("--signature-limit", type=int, default=40, help="Signatures to fetch per mint.")
    parser.add_argument("--max-transactions", type=int, default=20, help="Transactions to inspect per mint.")
    parser.add_argument("--max-buyers-per-mint", type=int, default=25, help="Buyer deltas to keep per mint.")
    parser.add_argument("--rpc-timeout", type=int, default=15, help="Read-only RPC timeout in seconds.")
    parser.add_argument("--write", action="store_true", help=f"Write {CANDIDATE_WALLETS.relative_to(ROOT)}.")
    parser.add_argument("--output", default=str(CANDIDATE_WALLETS), help="Output path when --write is set.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report = build_candidate_report(args)
    if args.write:
        atomic_write_json(args.output, report)
        print(f"Wrote {Path(args.output)}")
    else:
        print(json.dumps({
            "mode": report["mode"],
            "summary": report["summary"],
            "source_counts": report["source_counts"],
            "top_candidates": report["candidates"][:10],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
