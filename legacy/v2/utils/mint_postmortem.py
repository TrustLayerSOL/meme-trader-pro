#!/usr/bin/env python3
"""
Read-only mint miss postmortem.

Explains why MemeTraderPro did not record a token:
- scanner/bot/websocket offline or stale,
- no tracked wallet overlap,
- tracked wallet appears in account keys but not as token-balance owner,
- tracked token-owner delta exists and should have been parsed.

This tool does not write state, place trades, or touch watchlists.
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

import sys

sys.path.insert(0, str(ROOT))

from core.env_loader import load_env


RUNTIME_STATUS = ROOT / "data" / "runtime_status.json"
TRACKED_WALLETS = ROOT / "data" / "tracked_wallets.json"
LIVE_STATE_FILES = [
    ROOT / "data" / "live_state.json",
    ROOT / "live_state.json",
]
SQLITE_DB = ROOT / "data" / "memetrader.db"


def utc_from_ts(ts):
    if not ts:
        return "unknown"
    return datetime.fromtimestamp(float(ts), timezone.utc).isoformat()


def safe_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def load_tracked_wallets():
    data = safe_json(TRACKED_WALLETS, [])
    wallets = {}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            address = item.get("trackedWalletAddress") or item.get("address")
            if address:
                wallets[address] = item
    elif isinstance(data, dict):
        for address, value in data.items():
            wallets[address] = value if isinstance(value, dict) else {"name": value}
    return wallets


def component_age_seconds(component):
    status = safe_json(RUNTIME_STATUS, {})
    block = status.get(component) if isinstance(status, dict) else {}
    if not isinstance(block, dict):
        return None, "missing"

    updated = block.get("updated_at")
    if updated is None:
        return None, block.get("status") or "missing"

    try:
        return time.time() - float(updated), block.get("status") or "unknown"
    except Exception:
        return None, block.get("status") or "bad_timestamp"


def runtime_findings(stale_after=90):
    rows = []
    for component in ["bot", "websocket", "scanner"]:
        age, status = component_age_seconds(component)
        if age is None:
            verdict = "FAIL"
            detail = "missing heartbeat"
        elif age > stale_after:
            verdict = "FAIL"
            detail = f"stale heartbeat ({int(age)}s old)"
        else:
            verdict = "OK"
            detail = f"{status}, {int(age)}s old"
        rows.append({
            "component": component,
            "verdict": verdict,
            "detail": detail,
        })
    return rows


def local_state_contains(mint):
    hits = []
    for path in LIVE_STATE_FILES + [ROOT / "data" / "manual_watchlist.json", ROOT / "data" / "candidate_ledger.json", ROOT / "data" / "paper_trades.json"]:
        if path.exists() and mint in path.read_text(errors="ignore"):
            hits.append(str(path.relative_to(ROOT)))
    return hits


def sqlite_contains(mint):
    if not SQLITE_DB.exists():
        return []
    try:
        import sqlite3
        hits = []
        with sqlite3.connect(SQLITE_DB) as conn:
            for table in ["events", "alerts", "trades", "watchlist"]:
                try:
                    count = conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE mint=? OR payload_json LIKE ?",
                        (mint, f"%{mint}%"),
                    ).fetchone()[0]
                except Exception:
                    count = 0
                if count:
                    hits.append(f"{table}:{count}")
        return hits
    except Exception as exc:
        return [f"sqlite_error:{exc}"]


class HeliusRpc:
    def __init__(self, api_key):
        self.url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

    def call(self, method, params):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }).encode("utf-8")
        request = Request(
            self.url,
            data=payload,
            headers={"content-type": "application/json"},
        )
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())


def pubkey_of(account):
    if isinstance(account, dict):
        return account.get("pubkey")
    return account


def balance_map(balances):
    result = {}
    for item in balances or []:
        owner = item.get("owner")
        mint = item.get("mint")
        amount = ((item.get("uiTokenAmount") or {}).get("uiAmount") or 0)
        if owner and mint:
            try:
                result[(owner, mint)] = float(amount)
            except Exception:
                result[(owner, mint)] = 0.0
    return result


def analyze_chain(mint, tracked_wallets, limit):
    load_env()
    api_key = os.getenv("HELIUS_API_KEY")
    if not api_key:
        return {
            "error": "missing_HELIUS_API_KEY",
            "signatures": 0,
            "account_key_hits": [],
            "token_owner_hits": [],
        }

    rpc = HeliusRpc(api_key)
    try:
        signatures = rpc.call("getSignaturesForAddress", [mint, {"limit": limit}]).get("result") or []
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return {
            "error": f"signature_fetch_failed: {exc}",
            "signatures": 0,
            "account_key_hits": [],
            "token_owner_hits": [],
        }

    account_key_hits = []
    token_owner_hits = []
    token_balance_events = 0

    for index, item in enumerate(signatures):
        signature = item.get("signature")
        if not signature:
            continue
        try:
            tx = rpc.call(
                "getTransaction",
                [
                    signature,
                    {
                        "encoding": "jsonParsed",
                        "maxSupportedTransactionVersion": 0,
                        "commitment": "confirmed",
                    },
                ],
            ).get("result")
        except Exception:
            continue

        if not tx:
            continue

        block_time = tx.get("blockTime")
        keys = [
            pubkey_of(account)
            for account in tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
        ]
        overlaps = [key for key in keys if key in tracked_wallets]
        if overlaps:
            account_key_hits.append({
                "index": index,
                "signature": signature,
                "time": utc_from_ts(block_time),
                "wallets": overlaps,
            })

        meta = tx.get("meta") or {}
        pre = balance_map(meta.get("preTokenBalances"))
        post = balance_map(meta.get("postTokenBalances"))
        for owner, token_mint in set(pre) | set(post):
            if token_mint != mint:
                continue
            delta = post.get((owner, token_mint), 0) - pre.get((owner, token_mint), 0)
            if abs(delta) < 1e-9:
                continue
            token_balance_events += 1
            if owner in tracked_wallets:
                token_owner_hits.append({
                    "index": index,
                    "signature": signature,
                    "time": utc_from_ts(block_time),
                    "wallet": owner,
                    "delta": delta,
                })

    return {
        "error": None,
        "signatures": len(signatures),
        "account_key_hits": account_key_hits,
        "token_owner_hits": token_owner_hits,
        "token_balance_events": token_balance_events,
    }


def classify(runtime_rows, local_hits, sqlite_hits, chain):
    if local_hits or sqlite_hits:
        return "RECORDED_LOCALLY"

    runtime_failed = [row for row in runtime_rows if row["verdict"] == "FAIL"]
    if runtime_failed and not chain.get("token_owner_hits"):
        if chain.get("account_key_hits"):
            return "SCANNER_OFFLINE_AND_PARSER_VISIBILITY_GAP"
        return "SCANNER_OFFLINE_OR_STALE"

    if chain.get("token_owner_hits"):
        return "PARSER_OR_PERSISTENCE_MISS"

    if chain.get("account_key_hits"):
        return "TRACKED_WALLET_ACCOUNT_KEY_ONLY"

    if chain.get("signatures", 0) > 0:
        return "NO_TRACKED_WALLET_OVERLAP"

    if chain.get("error"):
        return "CHAIN_LOOKUP_FAILED"

    return "NO_RECENT_CHAIN_ACTIVITY"


def wallet_label(wallet, tracked):
    meta = tracked.get(wallet, {})
    name = meta.get("name") if isinstance(meta, dict) else None
    emoji = meta.get("emoji") if isinstance(meta, dict) else None
    label = wallet
    if name or emoji:
        label += f" ({name or 'unnamed'} {emoji or ''})".rstrip()
    return label


def main():
    parser = argparse.ArgumentParser(description="Explain why a mint was missed by MemeTraderPro.")
    parser.add_argument("mint", help="Token mint / contract address")
    parser.add_argument("--limit", type=int, default=80, help="Recent signatures to inspect")
    parser.add_argument("--stale-after", type=int, default=90, help="Heartbeat stale threshold in seconds")
    args = parser.parse_args()

    tracked = load_tracked_wallets()
    runtime_rows = runtime_findings(stale_after=args.stale_after)
    local_hits = local_state_contains(args.mint)
    sqlite_hits = sqlite_contains(args.mint)
    chain = analyze_chain(args.mint, tracked, args.limit)
    category = classify(runtime_rows, local_hits, sqlite_hits, chain)

    print(f"MINT: {args.mint}")
    print(f"ROOT CAUSE CATEGORY: {category}")
    print()
    print("Runtime:")
    for row in runtime_rows:
        print(f"- {row['component']}: {row['verdict']} ({row['detail']})")
    print()
    print(f"Local file hits: {', '.join(local_hits) if local_hits else 'none'}")
    print(f"SQLite hits: {', '.join(sqlite_hits) if sqlite_hits else 'none'}")
    print()
    if chain.get("error"):
        print(f"Chain lookup error: {chain['error']}")
        return

    print(f"Recent signatures inspected: {chain['signatures']}")
    print(f"Token balance events for mint: {chain['token_balance_events']}")
    print(f"Tracked wallet account-key hits: {len(chain['account_key_hits'])}")
    for hit in chain["account_key_hits"][:10]:
        wallets = ", ".join(wallet_label(wallet, tracked) for wallet in hit["wallets"])
        print(f"  - {hit['time']} {hit['signature'][:12]}... {wallets}")
    print(f"Tracked wallet token-owner delta hits: {len(chain['token_owner_hits'])}")
    for hit in chain["token_owner_hits"][:10]:
        print(
            f"  - {hit['time']} {hit['signature'][:12]}... "
            f"{wallet_label(hit['wallet'], tracked)} delta={hit['delta']:.6f}"
        )

    print()
    print("Interpretation:")
    if category == "SCANNER_OFFLINE_AND_PARSER_VISIBILITY_GAP":
        print("- Bot/scanner heartbeat was missing or stale, so live detection was not running.")
        print("- A tracked wallet appeared in transaction account keys, but not as the token balance owner.")
        print("- Current scanner logic may miss this Axiom-style signal even when online.")
    elif category == "SCANNER_OFFLINE_OR_STALE":
        print("- Bot/scanner heartbeat was missing or stale during the check window.")
    elif category == "PARSER_OR_PERSISTENCE_MISS":
        print("- A tracked wallet token-owner delta exists; scanner should parse this if online.")
        print("- Investigate parser, websocket subscription, and persistence paths.")
    elif category == "TRACKED_WALLET_ACCOUNT_KEY_ONLY":
        print("- A tracked wallet appeared in transaction account keys, but no tracked token-owner delta was found.")
        print("- Add parser diagnostics for account-key-only tracked wallet involvement.")
    elif category == "NO_TRACKED_WALLET_OVERLAP":
        print("- Recent sampled transactions had no overlap with the local tracked wallet list.")
    elif category == "RECORDED_LOCALLY":
        print("- Mint already appears in local state or SQLite.")


if __name__ == "__main__":
    main()
