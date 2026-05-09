import json
import time
from pathlib import Path


DATA_SOURCES = [
    {
        "name": "Root live state",
        "path": Path("live_state.json"),
        "kind": "json",
        "fresh_seconds": 300,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "scanner / bot runtime",
    },
    {
        "name": "Data live state",
        "path": Path("data/live_state.json"),
        "kind": "json",
        "fresh_seconds": 300,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "runtime compatibility snapshot",
    },
    {
        "name": "Paper trades",
        "path": Path("data/paper_trades.json"),
        "kind": "json",
        "fresh_seconds": 1800,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "paper trader",
    },
    {
        "name": "Manual watchlist",
        "path": Path("data/manual_watchlist.json"),
        "kind": "json",
        "fresh_seconds": 900,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "dashboard / watchdog",
    },
    {
        "name": "Wallet performance",
        "path": Path("data/wallet_performance.json"),
        "kind": "json",
        "fresh_seconds": 86400,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "wallet performance analyzer",
    },
    {
        "name": "Wallet discovery status",
        "path": Path("data/wallet_discovery_status.json"),
        "kind": "json",
        "fresh_seconds": 900,
        "timestamp_keys": ["generated_at", "updated_at"],
        "owner": "wallet discovery scheduler",
    },
    {
        "name": "Wallet behavior",
        "path": Path("data/wallet_behavior.json"),
        "kind": "json",
        "fresh_seconds": 1800,
        "timestamp_keys": ["generated_at", "updated_at"],
        "owner": "wallet discovery scheduler",
    },
    {
        "name": "Candidate wallets",
        "path": Path("data/candidate_wallets.json"),
        "kind": "json",
        "fresh_seconds": 1800,
        "timestamp_keys": ["generated_at", "last_updated", "updated_at"],
        "owner": "wallet discovery scheduler",
    },
    {
        "name": "Paper-watch wallets",
        "path": Path("data/paper_watch_wallets.json"),
        "kind": "json",
        "fresh_seconds": 1800,
        "timestamp_keys": ["generated_at", "last_updated", "updated_at"],
        "owner": "wallet discovery scheduler",
    },
    {
        "name": "Candidate ledger",
        "path": Path("data/candidate_ledger.json"),
        "kind": "json",
        "fresh_seconds": None,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "dashboard operator actions",
    },
    {
        "name": "Catalyst cards",
        "path": Path("data/catalyst_cards.json"),
        "kind": "json",
        "fresh_seconds": 1800,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "catalyst card builder",
    },
    {
        "name": "Runtime status",
        "path": Path("data/runtime_status.json"),
        "kind": "json",
        "fresh_seconds": 300,
        "timestamp_keys": [],
        "owner": "runtime heartbeats",
    },
    {
        "name": "Bot settings",
        "path": Path("data/bot_settings.json"),
        "kind": "json",
        "fresh_seconds": None,
        "timestamp_keys": [],
        "owner": "settings manager",
    },
    {
        "name": "Social state",
        "path": Path("data/social_state.json"),
        "kind": "json",
        "fresh_seconds": 86400,
        "timestamp_keys": ["last_updated", "updated_at"],
        "owner": "social modules",
    },
    {
        "name": "Tracked wallets",
        "path": Path("data/tracked_wallets.json"),
        "kind": "json",
        "fresh_seconds": None,
        "timestamp_keys": [],
        "owner": "wallet tracker",
    },
    {
        "name": "SQLite store",
        "path": Path("data/memetrader.db"),
        "kind": "sqlite",
        "fresh_seconds": 1800,
        "timestamp_keys": [],
        "owner": "storage sync",
    },
]


def _safe_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f), None
    except Exception as exc:
        return None, str(exc)


def _numeric_timestamp(value):
    if value in [None, ""]:
        return None
    try:
        numeric = float(value)
        if numeric > 1000000000:
            return numeric
    except Exception:
        pass
    return None


def _find_timestamp(data, keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = _numeric_timestamp(data.get(key))
        if value is not None:
            return value

    # runtime_status.json stores timestamps per component, not at the root.
    nested_timestamps = []
    for value in data.values():
        if isinstance(value, dict):
            timestamp = _numeric_timestamp(value.get("updated_at"))
            if timestamp is not None:
                nested_timestamps.append(timestamp)

    if nested_timestamps:
        return max(nested_timestamps)

    return None


def _format_age(seconds):
    if seconds is None:
        return "N/A"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h"
    return f"{seconds / 86400:.1f}d"


def _status_for(age_seconds, fresh_seconds, missing=False, malformed=False):
    if missing:
        return "MISSING"
    if malformed:
        return "BROKEN"
    if fresh_seconds is None:
        return "OK"
    if age_seconds is None:
        return "UNKNOWN"
    if age_seconds <= fresh_seconds:
        return "FRESH"
    if age_seconds <= fresh_seconds * 3:
        return "STALE"
    return "OLD"


class DataFreshness:
    def __init__(self, sources=None):
        self.sources = sources or DATA_SOURCES

    def report(self):
        rows = []
        now = time.time()

        for source in self.sources:
            path = source["path"]
            fresh_seconds = source.get("fresh_seconds")

            if not path.exists():
                rows.append({
                    "source": source["name"],
                    "status": _status_for(None, fresh_seconds, missing=True),
                    "age": "N/A",
                    "size": "missing",
                    "path": str(path),
                    "owner": source.get("owner", ""),
                    "detail": "file missing",
                })
                continue

            stat = path.stat()
            mtime_age = max(0, now - stat.st_mtime)
            detail = "mtime"
            logical_age = None
            malformed = False

            if source.get("kind") == "json":
                data, error = _safe_json(path)
                if error:
                    malformed = True
                    detail = error
                else:
                    timestamp = _find_timestamp(data, source.get("timestamp_keys", []))
                    if timestamp is not None:
                        logical_age = max(0, now - timestamp)
                        detail = "logical timestamp"

            age = logical_age if logical_age is not None else mtime_age
            rows.append({
                "source": source["name"],
                "status": _status_for(age, fresh_seconds, malformed=malformed),
                "age": _format_age(age),
                "size": f"{stat.st_size:,} bytes",
                "path": str(path),
                "owner": source.get("owner", ""),
                "detail": detail,
            })

        counts = {}
        for row in rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1

        blocking = counts.get("MISSING", 0) + counts.get("BROKEN", 0)
        stale = counts.get("STALE", 0) + counts.get("OLD", 0) + counts.get("UNKNOWN", 0)

        if blocking:
            overall = "FAIL"
        elif stale:
            overall = "WARN"
        else:
            overall = "OK"

        return {
            "overall": overall,
            "counts": counts,
            "rows": rows,
        }
