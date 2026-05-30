import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from core.json_store import atomic_write_json
from core.storage import EventStore


CATALYST_CARDS_FILE = Path("data/catalyst_cards.json")


def safe_float(value, default=None):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def first_present(source, keys, default=None):
    if not isinstance(source, dict):
        return default
    for key in keys:
        value = source.get(key)
        if value not in [None, ""]:
            return value
    return default


def record_time(record):
    return safe_float(
        first_present(record, ["time", "timestamp", "last_signal_time", "entry_time", "close_time"]),
        0,
    ) or 0


def load_snapshot_payloads(limit=500, store=None):
    store = store or EventStore()
    limit = store.safe_limit(limit, default=500, maximum=2000)

    with store.connect() as conn:
        conn.row_factory = None
        rows = conn.execute(
            """
            SELECT time, mint, source, context, price, liquidity, risk_label, payload_json
            FROM token_snapshots
            ORDER BY time DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    snapshots = []
    for row in rows:
        time_value, mint, source, context, price, liquidity, risk_label, payload_json = row
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        payload.setdefault("time", time_value)
        payload.setdefault("timestamp", time_value)
        payload.setdefault("mint", mint)
        payload.setdefault("source", source)
        payload.setdefault("context", context)
        payload.setdefault("price", price)
        payload.setdefault("liquidity", liquidity)
        payload.setdefault("risk_label", risk_label)
        snapshots.append(payload)

    return snapshots


def build_catalyst_cards_from_snapshots(snapshots, generated_at=None):
    generated_at = generated_at or time.time()
    grouped = defaultdict(list)

    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue
        mint = snapshot.get("mint") or snapshot.get("token_mint")
        if not mint:
            continue
        grouped[mint].append(snapshot)

    cards = []
    for mint, items in grouped.items():
        items.sort(key=record_time)
        latest = items[-1] if items else {}
        scanner_items = [i for i in items if str(i.get("source")) == "scanner"]
        paper_items = [i for i in items if str(i.get("source")) == "paper_trader"]
        watchdog_items = [i for i in items if str(i.get("source")) in {"watchdog", "rug_watchdog"}]
        latest_signal = scanner_items[-1] if scanner_items else {}
        latest_paper = paper_items[-1] if paper_items else {}
        latest_watchdog = watchdog_items[-1] if watchdog_items else {}
        contexts = Counter(i.get("context") or "unknown" for i in items)

        thesis = build_thesis(latest_signal, latest_paper, latest_watchdog)
        outcome = build_outcome(latest_paper, latest_watchdog, contexts)

        card = {
            "mint": mint,
            "generated_at": generated_at,
            "first_seen": record_time(items[0]),
            "last_seen": record_time(latest),
            "name": first_present(latest_signal.get("market_info"), ["name"])
            or first_present(latest_paper.get("market_info"), ["name"]),
            "symbol": first_present(latest_signal.get("market_info"), ["symbol"])
            or first_present(latest_paper.get("market_info"), ["symbol"]),
            "contexts": dict(contexts),
            "sources": sorted({i.get("source") for i in items if i.get("source")}),
            "thesis": thesis,
            "outcome": outcome,
            "score": {
                "total": safe_float(first_present(latest_signal, ["total_score", "score"])),
                "threshold": safe_float(first_present(latest_signal, ["score_threshold", "threshold"])),
                "edge": safe_float(first_present(latest_signal, ["edge_score"])),
                "edge_verdict": latest_signal.get("edge_verdict"),
            },
            "wallets": {
                "count": first_present(latest_signal, ["wallet_count"]),
                "weighted_score": first_present(latest_signal, ["weighted_wallet_score"]),
                "addresses": first_present(latest_signal, ["wallets"], []),
            },
            "social": {
                "matched": bool(latest_signal.get("social_matched")),
                "account": latest_signal.get("social_account"),
                "keywords": latest_signal.get("social_keywords", []),
                "bonus": latest_signal.get("social_bonus"),
            },
            "risk": {
                "label": first_present(latest_watchdog, ["risk_label"], latest_signal.get("risk_label")),
                "score": first_present(latest_signal, ["risk_score"]),
                "mechanics": first_present(
                    latest_watchdog,
                    ["mechanics_risk", "token_mechanics_risk"],
                    latest_signal.get("token_mechanics_risk"),
                ),
                "warnings": first_present(latest_signal, ["risk_warnings"], []),
                "hard_block": bool(latest_signal.get("hard_block")),
            },
            "market": {
                "price": first_present(latest, ["price"]),
                "liquidity": first_present(latest, ["liquidity"]),
                "market_cap": first_present(latest, ["market_cap"]),
                "volume": first_present(latest_signal, ["volume"], first_present(latest_signal.get("market_info"), ["volume"])),
            },
            "paper": {
                "status": latest_paper.get("status"),
                "entry_price": latest_paper.get("entry_price"),
                "size_usd": latest_paper.get("size_usd"),
                "remaining_pct": latest_paper.get("remaining_pct"),
                "total_pnl": latest_paper.get("total_pnl"),
                "total_pnl_pct": latest_paper.get("total_pnl_pct"),
                "entry_reason": latest_paper.get("entry_reason"),
                "exit_reason": latest_paper.get("exit_reason"),
            },
            "snapshot_count": len(items),
        }
        cards.append(card)

    cards.sort(
        key=lambda card: (
            safe_float(card.get("score", {}).get("edge"), 0) or 0,
            safe_float(card.get("score", {}).get("total"), 0) or 0,
            card.get("last_seen") or 0,
        ),
        reverse=True,
    )
    return cards


def build_thesis(signal, paper, watchdog):
    thesis = []

    wallet_count = safe_float(signal.get("wallet_count"), 0) or 0
    weighted = safe_float(signal.get("weighted_wallet_score"), 0) or 0
    if wallet_count or weighted:
        thesis.append(f"wallet confirmation: {int(wallet_count)} wallet(s), weighted score {weighted:g}")

    if signal.get("social_matched"):
        account = signal.get("social_account") or "unknown"
        keywords = ", ".join(str(k) for k in signal.get("social_keywords", [])[:4])
        thesis.append(f"social catalyst: @{account} matched {keywords or 'token narrative'}")

    if signal.get("edge_verdict"):
        thesis.append(f"edge verdict: {signal.get('edge_verdict')} ({signal.get('edge_score')})")

    risk_label = first_present(watchdog, ["risk_label"], signal.get("risk_label"))
    if risk_label:
        thesis.append(f"risk: {risk_label}")

    if paper.get("context") == "paper_entry_opened":
        thesis.append("paper outcome: entry opened")
    elif paper.get("context") == "paper_entry_failed":
        thesis.append(f"paper outcome: entry failed ({paper.get('failure_reason')})")

    return thesis[:8]


def build_outcome(paper, watchdog, contexts):
    if paper.get("context") == "paper_exit_closed":
        pnl = safe_float(paper.get("total_pnl"), 0) or 0
        pnl_pct = safe_float(paper.get("total_pnl_pct"), 0) or 0
        return {
            "status": "closed",
            "summary": f"closed paper trade: {pnl:.2f} USD / {pnl_pct:.2f}%",
        }

    if paper.get("context") == "paper_partial_exit":
        return {
            "status": "partial_exit",
            "summary": f"partial paper exit, remaining {paper.get('remaining_pct')}%",
        }

    if paper.get("context") == "paper_entry_opened":
        return {
            "status": "open",
            "summary": "paper trade open",
        }

    if contexts.get("scanner_skip"):
        return {
            "status": "skipped",
            "summary": "scanner skipped before paper entry",
        }

    if watchdog:
        return {
            "status": "protected_watch",
            "summary": f"watchdog latest risk {watchdog.get('risk_label')}",
        }

    return {
        "status": "observed",
        "summary": "observed candidate",
    }


class CatalystCardBuilder:
    def __init__(self, store=None):
        self.store = store or EventStore()

    def build(self, limit=500):
        return build_catalyst_cards_from_snapshots(
            load_snapshot_payloads(limit=limit, store=self.store)
        )

    def save(self, path=CATALYST_CARDS_FILE, limit=500):
        cards = self.build(limit=limit)
        payload = {
            "last_updated": time.time(),
            "count": len(cards),
            "cards": cards,
        }
        atomic_write_json(path, payload)
        return payload


if __name__ == "__main__":
    result = CatalystCardBuilder().save()
    print(json.dumps({"count": result["count"], "path": str(CATALYST_CARDS_FILE)}, indent=2))
