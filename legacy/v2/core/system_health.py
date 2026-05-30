import json
import os
import stat
import time
from pathlib import Path

from core.env_loader import load_env
from core.storage import DB_FILE, EventStore


load_env()


REQUIRED_JSON_FILES = {
    "live_state": Path("live_state.json"),
    "paper_trades": Path("data/paper_trades.json"),
    "wallet_performance": Path("data/wallet_performance.json"),
    "manual_watchlist": Path("data/manual_watchlist.json"),
    "runtime_status": Path("data/runtime_status.json"),
    "tracked_wallets": Path("data/tracked_wallets.json"),
}
CRITICAL_RUNTIME_COMPONENTS = {"bot", "websocket", "scanner"}
RUNTIME_HEARTBEAT_FRESH_SECONDS = 300
PRIVATE_PERMISSION_FILES = [
    Path(".env"),
    DB_FILE,
    Path(str(DB_FILE) + "-wal"),
    Path(str(DB_FILE) + "-shm"),
]


class SystemHealth:
    def safe_load_json(self, path):
        try:
            with open(path, "r") as f:
                return json.load(f), None
        except Exception as exc:
            return None, str(exc)

    def age_seconds(self, timestamp):
        try:
            if timestamp in [None, ""]:
                return None
            return max(0, time.time() - float(timestamp))
        except Exception:
            return None

    def status(self, ok, warning=False):
        if ok:
            return "OK"
        if warning:
            return "WARN"
        return "FAIL"

    def check_api_keys(self):
        rows = []
        for key in ["HELIUS_API_KEY", "JUPITER_API_KEY"]:
            present = bool(os.getenv(key))
            rows.append({
                "check": key,
                "status": self.status(present),
                "detail": "present" if present else "missing",
            })
        return rows

    def check_files(self):
        rows = []
        for name, path in REQUIRED_JSON_FILES.items():
            if not path.exists():
                rows.append({
                    "check": name,
                    "status": "FAIL",
                    "detail": f"{path} missing",
                })
                continue

            data, error = self.safe_load_json(path)
            if error:
                rows.append({
                    "check": name,
                    "status": "FAIL",
                    "detail": error,
                })
                continue

            rows.append({
                "check": name,
                "status": "OK",
                "detail": f"{path} valid",
            })

        return rows

    def check_private_permissions(self):
        rows = []
        if os.name == "nt":
            return rows

        for path in PRIVATE_PERMISSION_FILES:
            if not path.exists():
                continue
            try:
                mode = stat.S_IMODE(path.stat().st_mode)
            except Exception as exc:
                rows.append({
                    "check": f"permissions_{path.name}",
                    "status": "WARN",
                    "detail": f"unable to inspect {path}: {exc}",
                })
                continue

            exposed = bool(mode & 0o077)
            rows.append({
                "check": f"permissions_{path.name}",
                "status": self.status(not exposed),
                "detail": f"{path} mode {mode:03o}; expected 600",
            })

        return rows

    def check_state_quality(self):
        rows = []

        live, _ = self.safe_load_json("live_state.json")
        if isinstance(live, dict):
            events = live.get("events", [])
            alerts = live.get("alerts", [])
            age = self.age_seconds(live.get("last_updated"))
            rows.append({
                "check": "live_state_events",
                "status": self.status(len(events) > 0, warning=True),
                "detail": f"{len(events)} events",
            })
            rows.append({
                "check": "live_state_alerts",
                "status": self.status(len(alerts) > 0, warning=True),
                "detail": f"{len(alerts)} alerts",
            })
            rows.append({
                "check": "live_state_freshness",
                "status": self.status(age is not None and age < 300, warning=True),
                "detail": "never updated" if age is None else f"{age:.0f}s old",
            })

        trades, _ = self.safe_load_json("data/paper_trades.json")
        if isinstance(trades, dict):
            rows.append({
                "check": "paper_trade_state",
                "status": "OK",
                "detail": (
                    f"{len(trades.get('open_trades', []))} open, "
                    f"{len(trades.get('closed_trades', []))} closed, "
                    f"{len(trades.get('failed_trades', []))} failed"
                ),
            })

        wallets, _ = self.safe_load_json("data/tracked_wallets.json")
        if isinstance(wallets, list):
            rows.append({
                "check": "tracked_wallets",
                "status": self.status(len(wallets) >= 100, warning=True),
                "detail": f"{len(wallets)} wallets",
            })

        runtime, _ = self.safe_load_json("data/runtime_status.json")
        if isinstance(runtime, dict):
            for component in [
                "bot",
                "websocket",
                "scanner",
                "market",
                "quotes",
                "watchdog",
                "wallet_discovery",
                "forward_wallet_activity",
            ]:
                item = runtime.get(component, {})
                age = self.age_seconds(item.get("updated_at")) if isinstance(item, dict) else None
                is_fresh = age is not None and age < RUNTIME_HEARTBEAT_FRESH_SECONDS
                critical = component in CRITICAL_RUNTIME_COMPONENTS
                rows.append({
                    "check": f"runtime_{component}",
                    "status": self.status(is_fresh, warning=not critical),
                    "detail": "no heartbeat" if age is None else f"{age:.0f}s old",
                })

        return rows

    def check_logs(self):
        rows = []
        log_dir = Path("logs")
        expected = {
            "bot_log": log_dir / "bot.log",
            "dashboard_log": log_dir / "dashboard.log",
            "watchdog_log": log_dir / "watchdog.log",
        }

        for name, path in expected.items():
            if not path.exists():
                rows.append({
                    "check": name,
                    "status": "WARN",
                    "detail": "not created yet",
                })
                continue

            size = path.stat().st_size
            rows.append({
                "check": name,
                "status": self.status(size > 0, warning=True),
                "detail": f"{size} bytes",
            })

        return rows

    def check_database(self):
        if not DB_FILE.exists():
            return [{
                "check": "sqlite_store",
                "status": "WARN",
                "detail": "data/memetrader.db not created yet",
            }]

        try:
            counts = EventStore(DB_FILE).counts()
        except Exception as exc:
            return [{
                "check": "sqlite_store",
                "status": "FAIL",
                "detail": str(exc),
            }]

        return [{
            "check": "sqlite_store",
            "status": self.status(counts.get("events", 0) > 0 or counts.get("alerts", 0) > 0, warning=True),
            "detail": (
                f"{counts.get('events', 0)} events, "
                f"{counts.get('alerts', 0)} alerts, "
                f"{counts.get('trades', 0)} trades, "
                f"{counts.get('watchlist', 0)} protected"
            ),
        }]

    def report(self):
        rows = []
        rows.extend(self.check_api_keys())
        rows.extend(self.check_files())
        rows.extend(self.check_private_permissions())
        rows.extend(self.check_state_quality())
        rows.extend(self.check_logs())
        rows.extend(self.check_database())

        counts = {
            "OK": len([row for row in rows if row["status"] == "OK"]),
            "WARN": len([row for row in rows if row["status"] == "WARN"]),
            "FAIL": len([row for row in rows if row["status"] == "FAIL"]),
        }

        if counts["FAIL"]:
            overall = "FAIL"
        elif counts["WARN"]:
            overall = "WARN"
        else:
            overall = "OK"

        return {
            "overall": overall,
            "counts": counts,
            "rows": rows,
        }
