import json
import sqlite3
import time
from pathlib import Path


DB_FILE = Path("data/memetrader.db")


class EventStore:
    def __init__(self, path=DB_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        return sqlite3.connect(self.path)

    def init_db(self):
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time REAL,
                    event_type TEXT,
                    wallet TEXT,
                    mint TEXT,
                    payload_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time REAL,
                    mint TEXT,
                    signal_type TEXT,
                    total_score REAL,
                    edge_score REAL,
                    edge_verdict TEXT,
                    should_trade INTEGER,
                    risk_label TEXT,
                    payload_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mint TEXT,
                    status TEXT,
                    entry_time REAL,
                    close_time REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    reason TEXT,
                    payload_json TEXT,
                    UNIQUE(mint, status, entry_time, close_time)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    mint TEXT PRIMARY KEY,
                    status TEXT,
                    risk_level TEXT,
                    updated_at TEXT,
                    payload_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_mint ON events(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_mint ON alerts(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_edge ON alerts(edge_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_mint ON trades(mint)")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_events_unique
                ON events(time, event_type, wallet, mint)
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_unique
                ON alerts(time, mint, signal_type)
                """
            )
            conn.execute(
                """
                DELETE FROM trades
                WHERE id NOT IN (
                    SELECT MIN(id)
                    FROM trades
                    GROUP BY mint, status, entry_time, COALESCE(close_time, -1)
                )
                """
            )

    def insert_event(self, event):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO events (time, event_type, wallet, mint, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.get("time") or event.get("timestamp") or time.time(),
                    event.get("type"),
                    event.get("wallet"),
                    event.get("mint"),
                    json.dumps(event),
                ),
            )

    def insert_alert(self, alert):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO alerts (
                    time, mint, signal_type, total_score, edge_score,
                    edge_verdict, should_trade, risk_label, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.get("time") or alert.get("timestamp") or time.time(),
                    alert.get("mint"),
                    alert.get("type"),
                    self.safe_float(alert.get("total_score")),
                    self.safe_float(alert.get("edge_score")),
                    alert.get("edge_verdict"),
                    1 if alert.get("should_trade") else 0,
                    alert.get("risk_label"),
                    json.dumps(alert),
                ),
            )

    def upsert_trade(self, trade):
        with self.connect() as conn:
            mint = trade.get("token_mint") or trade.get("mint")
            status = trade.get("status")
            entry_time = self.safe_float(trade.get("entry_time"))
            close_time = self.safe_float(trade.get("close_time"))
            conn.execute(
                """
                DELETE FROM trades
                WHERE mint IS ?
                  AND status IS ?
                  AND entry_time IS ?
                  AND COALESCE(close_time, -1) = COALESCE(?, -1)
                """,
                (mint, status, entry_time, close_time),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO trades (
                    mint, status, entry_time, close_time, pnl, pnl_pct, reason, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mint,
                    status,
                    entry_time,
                    close_time,
                    self.safe_float(trade.get("total_pnl", trade.get("pnl"))),
                    self.safe_float(trade.get("total_pnl_pct", trade.get("pnl_pct"))),
                    trade.get("entry_reason") or trade.get("reason"),
                    json.dumps(trade),
                ),
            )

    def upsert_watchlist_item(self, item):
        mint = item.get("token_mint")
        if not mint:
            return

        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO watchlist (
                    mint, status, risk_level, updated_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    mint,
                    item.get("status"),
                    item.get("risk_level"),
                    item.get("last_update"),
                    json.dumps(item),
                ),
            )

    def counts(self):
        with self.connect() as conn:
            return {
                "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                "alerts": conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
                "trades": conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
                "watchlist": conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0],
            }

    def recent_events(self, limit=25):
        limit = self.safe_limit(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT time, event_type, wallet, mint
                FROM events
                ORDER BY time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_alerts(self, limit=25):
        limit = self.safe_limit(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT time, mint, signal_type, total_score, edge_score,
                       edge_verdict, should_trade, risk_label
                FROM alerts
                ORDER BY time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_trades(self, limit=25):
        limit = self.safe_limit(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT mint, status, entry_time, close_time, pnl, pnl_pct, reason
                FROM trades
                ORDER BY COALESCE(close_time, entry_time, 0) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def watchlist_rows(self):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT mint, status, risk_level, updated_at
                FROM watchlist
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def top_alert_mints(self, limit=15):
        limit = self.safe_limit(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT mint,
                       COUNT(*) AS alerts,
                       MAX(edge_score) AS max_edge,
                       MAX(total_score) AS max_score,
                       MAX(time) AS last_seen
                FROM alerts
                WHERE mint IS NOT NULL AND mint != ''
                GROUP BY mint
                ORDER BY alerts DESC, max_edge DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def trade_summary(self):
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT COUNT(*) AS trades,
                       SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_trades,
                       SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) AS closed_trades,
                       SUM(COALESCE(pnl, 0)) AS total_pnl,
                       AVG(COALESCE(pnl_pct, 0)) AS avg_pnl_pct,
                       SUM(CASE WHEN COALESCE(pnl, 0) > 0 THEN 1 ELSE 0 END) AS winners
                FROM trades
                """
            ).fetchone()
        return dict(row) if row else {}

    def safe_float(self, value):
        try:
            if value in [None, ""]:
                return None
            return float(value)
        except Exception:
            return None

    def safe_limit(self, value, default=25, maximum=250):
        try:
            value = int(value)
        except Exception:
            value = default
        return max(1, min(maximum, value))
