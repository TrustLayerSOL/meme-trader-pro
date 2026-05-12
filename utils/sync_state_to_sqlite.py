import json
import sys
import argparse
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.storage import EventStore
from core.decision_ledger import build_decision_record, build_trade_result


def load_json(path, default):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def trade_rows(trades):
    trades = trades if isinstance(trades, dict) else {}
    bucket_status = {
        "open_trades": "open",
        "closed_trades": "closed",
        "failed_trades": "failed",
    }
    for key in ("open_trades", "closed_trades", "failed_trades"):
        for trade in trades.get(key, []) if isinstance(trades.get(key), list) else []:
            if isinstance(trade, dict):
                item = dict(trade)
                item.setdefault("status", bucket_status[key])
                yield item


def expected_trade_counts(trades):
    trades = trades if isinstance(trades, dict) else {}
    return {
        key: len(trades.get(key, []) if isinstance(trades.get(key), list) else [])
        for key in ("open_trades", "closed_trades", "failed_trades")
    }


def sqlite_trade_counts(store):
    with store.connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) FROM trades GROUP BY status").fetchall()
    counts = {"open_trades": 0, "closed_trades": 0, "failed_trades": 0}
    for status, count in rows:
        key = {
            "open": "open_trades",
            "closed": "closed_trades",
            "failed": "failed_trades",
        }.get(status)
        if key:
            counts[key] += int(count)
    return counts


def sync_trades(store, trades, rebuild=False):
    if rebuild:
        with store.connect() as conn:
            conn.execute("DELETE FROM trades")
    for trade in trade_rows(trades):
        store.upsert_trade(trade)
    expected = expected_trade_counts(trades)
    actual = sqlite_trade_counts(store)
    return {
        "expected": expected,
        "actual": actual,
        "parity": expected == actual,
    }


def trade_decision_id(trade):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    return trade.get("decision_id") or metadata.get("decision_id")


def trade_paper_lane(trade):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    if trade.get("exploration") is True:
        return "exploration"
    return trade.get("paper_lane") or metadata.get("paper_lane") or "main"


def synthetic_trade_decision_id(trade, bucket):
    trade = trade if isinstance(trade, dict) else {}
    parts = [
        bucket,
        str(trade.get("mint") or trade.get("token_mint") or ""),
        str(trade.get("entry_time") or trade.get("time") or ""),
        str(trade.get("close_time") or trade.get("exit_time") or ""),
        str(trade.get("entry_reason") or trade.get("reason") or ""),
    ]
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"dec_legacy_paper_{digest}"


def synthetic_decision_payload_from_trade(trade, bucket, decision_id):
    trade = trade if isinstance(trade, dict) else {}
    metadata = trade.get("signal_metadata") if isinstance(trade.get("signal_metadata"), dict) else {}
    timestamp = trade.get("entry_time") or trade.get("time") or trade.get("close_time")
    should_trade = bucket in {"open_trades", "closed_trades"}
    reason = (
        trade.get("entry_reason")
        or trade.get("reason")
        or trade.get("failure_reason")
        or trade.get("close_reason")
        or "legacy paper trade"
    )
    buy_quote_pass = "quote_ok" in str(reason)
    return build_decision_record({
        "decision_id": decision_id,
        "timestamp": timestamp,
        "mint": trade.get("mint") or trade.get("token_mint"),
        "type": metadata.get("signal_type") or "legacy_paper_trade",
        "paper_lane": trade_paper_lane(trade),
        "should_trade": should_trade,
        "wallets": trade.get("wallets") or [],
        "wallet_count": len(trade.get("wallets") or []),
        "position_size_usd": trade.get("position_size_usd") or trade.get("size_usd"),
        "buy_quote_pass": buy_quote_pass,
        "sell_quote_pass": buy_quote_pass,
        "risk_label": metadata.get("risk_label"),
        "risk_score": metadata.get("risk_score"),
        "total_score": metadata.get("score") or metadata.get("total_score"),
        "threshold": metadata.get("threshold"),
        "edge_score": (metadata.get("edge_result") or {}).get("edge_score") if isinstance(metadata.get("edge_result"), dict) else metadata.get("edge_score"),
        "edge_verdict": (metadata.get("edge_result") or {}).get("edge_verdict") if isinstance(metadata.get("edge_result"), dict) else metadata.get("edge_verdict"),
        "score_reasons": [reason, "synthetic legacy paper decision backfill"],
    })


def ensure_trade_decision(store, trade, bucket, create_missing=False):
    decision_id = trade_decision_id(trade)
    created = False
    if not decision_id and create_missing:
        decision_id = synthetic_trade_decision_id(trade, bucket)
    if not decision_id:
        return None, created
    if create_missing:
        store.upsert_decision(synthetic_decision_payload_from_trade(trade, bucket, decision_id))
        created = not bool(trade_decision_id(trade))
    return decision_id, created


def sync_decision_results(store, trades, create_missing=False):
    contexts = {
        "open_trades": ("paper_entry_opened", "paper_opened"),
        "closed_trades": ("paper_exit_closed", "paper_closed"),
        "failed_trades": ("paper_entry_failed", "paper_failed"),
    }
    updated = 0
    created = 0
    missing_decision_id = 0
    missing_record = 0
    for key, (context, final_action) in contexts.items():
        rows = trades.get(key) if isinstance(trades, dict) and isinstance(trades.get(key), list) else []
        for trade in rows:
            if not isinstance(trade, dict):
                continue
            trade = dict(trade)
            trade.setdefault("status", {
                "open_trades": "open",
                "closed_trades": "closed",
                "failed_trades": "failed",
            }[key])
            decision_id, did_create = ensure_trade_decision(store, trade, key, create_missing=create_missing)
            if not decision_id:
                missing_decision_id += 1
                continue
            if did_create:
                created += 1
            action_updated = store.update_decision_action(decision_id, {
                "scanner_stage": "paper_entry" if key == "open_trades" else "paper_exit" if key == "closed_trades" else "paper_buy_fill",
                "final_action": final_action,
                "reason": trade.get("failure_reason") or trade.get("exit_reason") or trade.get("close_reason") or trade.get("reason") or context,
                "paper_lane": trade_paper_lane(trade),
                "position_size_usd": trade.get("position_size_usd") or trade.get("size_usd"),
            })
            result_updated = store.update_decision_result(
                decision_id,
                build_trade_result(trade, context),
            )
            if action_updated or result_updated:
                updated += 1
            else:
                missing_record += 1
    return {
        "updated": updated,
        "created": created,
        "missing_decision_id": missing_decision_id,
        "missing_record": missing_record,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-trades", action="store_true", help="Delete and rebuild only SQLite trades from data/paper_trades.json before syncing other state.")
    args = parser.parse_args()

    live = load_json(ROOT / "live_state.json", {"events": [], "alerts": []})
    trades = load_json(ROOT / "data" / "paper_trades.json", {})
    watchlist = load_json(ROOT / "data" / "manual_watchlist.json", [])

    store = EventStore(ROOT / "data" / "memetrader.db")

    for event in live.get("events", []):
        store.insert_event(event)

    for alert in live.get("alerts", []):
        store.insert_alert(alert)

    trade_sync = sync_trades(store, trades, rebuild=args.rebuild_trades)
    decision_sync = sync_decision_results(store, trades, create_missing=True)

    for item in watchlist:
        store.upsert_watchlist_item(item)

    print({"counts": store.counts(), "trade_sync": trade_sync, "decision_sync": decision_sync})


if __name__ == "__main__":
    main()
