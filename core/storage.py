import json
import os
import sqlite3
import time
import uuid
from pathlib import Path


DB_FILE = Path("data/memetrader.db")


class EventStore:
    def __init__(self, path=DB_FILE):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
        self.secure_file_permissions()
        return conn

    def secure_file_permissions(self):
        for path in [self.path, self.path.with_name(self.path.name + "-wal"), self.path.with_name(self.path.name + "-shm")]:
            try:
                if path.exists() and os.name != "nt":
                    os.chmod(path, 0o600)
            except Exception:
                pass

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
            self.ensure_watchlist_wallet_key(conn)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time REAL,
                    mint TEXT,
                    source TEXT,
                    context TEXT,
                    price REAL,
                    liquidity REAL,
                    risk_label TEXT,
                    payload_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swap_ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time REAL,
                    mint TEXT,
                    signature TEXT,
                    wallet TEXT,
                    side TEXT,
                    price REAL,
                    market_cap REAL,
                    liquidity REAL,
                    token_amount REAL,
                    sol_amount REAL,
                    source TEXT,
                    payload_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_records (
                    decision_id TEXT PRIMARY KEY,
                    created_at REAL,
                    updated_at REAL,
                    mint TEXT,
                    signal_type TEXT,
                    scanner_stage TEXT,
                    final_action TEXT,
                    action_reason TEXT,
                    paper_lane TEXT,
                    should_trade INTEGER,
                    total_score REAL,
                    threshold REAL,
                    edge_score REAL,
                    edge_verdict TEXT,
                    risk_label TEXT,
                    risk_score REAL,
                    buy_quote_pass INTEGER,
                    sell_quote_pass INTEGER,
                    position_size_usd REAL,
                    trade_id TEXT,
                    trade_status TEXT,
                    entry_time REAL,
                    close_time REAL,
                    pnl REAL,
                    pnl_pct REAL,
                    payload_json TEXT,
                    result_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_mint ON events(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_mint ON alerts(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_edge ON alerts(edge_score)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_mint ON trades(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_snapshots_mint ON token_snapshots(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_snapshots_time ON token_snapshots(time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_snapshots_mint_time_desc ON token_snapshots(mint, time DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swap_ticks_mint_time ON swap_ticks(mint, time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swap_ticks_mint_time_id_desc ON swap_ticks(mint, time DESC, id DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_swap_ticks_time ON swap_ticks(time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_records_mint ON decision_records(mint)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_records_updated ON decision_records(updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_records_action ON decision_records(final_action, paper_lane)")
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_swap_ticks_signature
                ON swap_ticks(signature, mint)
                WHERE signature IS NOT NULL AND signature != ''
                """
            )
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
                "PRAGMA user_version = 1"
            )

    def ensure_watchlist_wallet_key(self, conn):
        rows = conn.execute("PRAGMA table_info(watchlist)").fetchall()
        columns = [row[1] for row in rows]
        pk_columns = [row[1] for row in rows if row[5]]
        if "wallet" in columns and set(pk_columns) == {"mint", "wallet"}:
            return

        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_new (
                mint TEXT,
                wallet TEXT DEFAULT '',
                status TEXT,
                risk_level TEXT,
                updated_at TEXT,
                payload_json TEXT,
                PRIMARY KEY (mint, wallet)
            )
        """)
        wallet_expr = "wallet" if "wallet" in columns else "''"
        conn.execute(f"""
            INSERT OR REPLACE INTO watchlist_new (
                mint, wallet, status, risk_level, updated_at, payload_json
            )
            SELECT mint, COALESCE({wallet_expr}, ''), status, risk_level, updated_at, payload_json
            FROM watchlist
        """)
        conn.execute("DROP TABLE watchlist")
        conn.execute("ALTER TABLE watchlist_new RENAME TO watchlist")

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
            status = self.trade_status(trade)
            entry_time = self.safe_float(trade.get("entry_time") or trade.get("time"))
            close_time = self.safe_float(trade.get("close_time") or trade.get("exit_time"))
            reason = self.trade_reason(trade)
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
            if status in {"closed", "failed"}:
                conn.execute(
                    """
                    DELETE FROM trades
                    WHERE mint IS ?
                      AND status = 'open'
                      AND entry_time IS ?
                    """,
                    (mint, entry_time),
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
                    reason,
                    json.dumps(trade),
                ),
            )

    def trade_status(self, trade):
        status = str(trade.get("status") or "").lower()
        if (
            "fail" in status
            or trade.get("failure_reason")
            or trade.get("failed_reason")
            or trade.get("error")
            or trade.get("buy_failed")
            or (not status and str(trade.get("side") or "").lower() == "buy" and not trade.get("entry_time"))
        ):
            return "failed"
        if (
            status in {"closed", "sold", "exited"}
            or "closed" in status
            or trade.get("close_time")
            or trade.get("exit_time")
            or trade.get("exit_reason")
            or trade.get("close_reason")
        ):
            return "closed"
        return status or "open"

    def trade_reason(self, trade):
        return (
            trade.get("exit_reason")
            or trade.get("close_reason")
            or trade.get("failure_reason")
            or trade.get("failed_reason")
            or trade.get("entry_reason")
            or trade.get("reason")
            or trade.get("error")
        )

    def upsert_watchlist_item(self, item):
        mint = item.get("token_mint")
        if not mint:
            return

        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO watchlist (
                    mint, wallet, status, risk_level, updated_at, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    mint,
                    item.get("wallet") or "",
                    item.get("status"),
                    item.get("risk_level"),
                    item.get("last_update"),
                    json.dumps(item),
                ),
            )

    def insert_token_snapshot(self, snapshot):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO token_snapshots (
                    time, mint, source, context, price, liquidity, risk_label, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.get("time") or snapshot.get("timestamp") or time.time(),
                    snapshot.get("mint") or snapshot.get("token_mint"),
                    snapshot.get("source"),
                    snapshot.get("context"),
                    self.safe_float(snapshot.get("price")),
                    self.safe_float(snapshot.get("liquidity")),
                    snapshot.get("risk_label"),
                    json.dumps(snapshot),
                ),
            )

    def insert_swap_tick(self, tick):
        tick = tick if isinstance(tick, dict) else {}
        mint = tick.get("mint") or tick.get("token_mint")
        timestamp = self.safe_float(tick.get("time") or tick.get("timestamp"))
        price = self.safe_float(tick.get("price"))
        if not mint or timestamp is None or price is None or price <= 0:
            return False

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO swap_ticks (
                    time, mint, signature, wallet, side, price, market_cap,
                    liquidity, token_amount, sol_amount, source, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    mint,
                    tick.get("signature") or tick.get("tx_signature"),
                    tick.get("wallet"),
                    tick.get("side") or tick.get("type"),
                    price,
                    self.safe_float(tick.get("market_cap")),
                    self.safe_float(tick.get("liquidity") or tick.get("liquidity_usd")),
                    self.safe_float(tick.get("token_amount") or tick.get("amount")),
                    self.safe_float(tick.get("sol_amount") or tick.get("native_amount")),
                    tick.get("source") or "unknown",
                    json.dumps(tick),
                ),
            )
        return cursor.rowcount > 0

    def upsert_decision(self, decision):
        decision = decision if isinstance(decision, dict) else {}
        decision_id = decision.get("decision_id") or f"dec_{uuid.uuid4().hex}"
        now = time.time()
        created_at = self.safe_float(decision.get("created_at")) or now
        updated_at = self.safe_float(decision.get("updated_at")) or now
        payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else decision

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO decision_records (
                    decision_id, created_at, updated_at, mint, signal_type,
                    scanner_stage, final_action, action_reason, paper_lane,
                    should_trade, total_score, threshold, edge_score, edge_verdict,
                    risk_label, risk_score, buy_quote_pass, sell_quote_pass,
                    position_size_usd, trade_id, trade_status, entry_time,
                    close_time, pnl, pnl_pct, payload_json, result_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    mint=excluded.mint,
                    signal_type=excluded.signal_type,
                    scanner_stage=excluded.scanner_stage,
                    final_action=excluded.final_action,
                    action_reason=excluded.action_reason,
                    paper_lane=excluded.paper_lane,
                    should_trade=excluded.should_trade,
                    total_score=excluded.total_score,
                    threshold=excluded.threshold,
                    edge_score=excluded.edge_score,
                    edge_verdict=excluded.edge_verdict,
                    risk_label=excluded.risk_label,
                    risk_score=excluded.risk_score,
                    buy_quote_pass=excluded.buy_quote_pass,
                    sell_quote_pass=excluded.sell_quote_pass,
                    position_size_usd=excluded.position_size_usd,
                    payload_json=excluded.payload_json
                """,
                (
                    decision_id,
                    created_at,
                    updated_at,
                    decision.get("mint"),
                    decision.get("signal_type"),
                    decision.get("scanner_stage"),
                    decision.get("final_action"),
                    decision.get("action_reason"),
                    decision.get("paper_lane"),
                    self.safe_bool_int(decision.get("should_trade")),
                    self.safe_float(decision.get("total_score")),
                    self.safe_float(decision.get("threshold")),
                    self.safe_float(decision.get("edge_score")),
                    decision.get("edge_verdict"),
                    decision.get("risk_label"),
                    self.safe_float(decision.get("risk_score")),
                    self.safe_bool_int(decision.get("buy_quote_pass")),
                    self.safe_bool_int(decision.get("sell_quote_pass")),
                    self.safe_float(decision.get("position_size_usd")),
                    decision.get("trade_id"),
                    decision.get("trade_status"),
                    self.safe_float(decision.get("entry_time")),
                    self.safe_float(decision.get("close_time")),
                    self.safe_float(decision.get("pnl")),
                    self.safe_float(decision.get("pnl_pct")),
                    json.dumps(payload, default=str),
                    json.dumps(decision.get("result"), default=str) if decision.get("result") is not None else None,
                ),
            )
        return decision_id

    def update_decision_action(self, decision_id, action):
        if not decision_id:
            return False
        action = action if isinstance(action, dict) else {}
        now = time.time()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT payload_json FROM decision_records WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return False
            payload = self.parse_json(row["payload_json"], {})
            payload.setdefault("action", {}).update(action)
            cursor = conn.execute(
                """
                UPDATE decision_records
                SET updated_at = ?,
                    scanner_stage = COALESCE(?, scanner_stage),
                    final_action = COALESCE(?, final_action),
                    action_reason = COALESCE(?, action_reason),
                    paper_lane = COALESCE(?, paper_lane),
                    position_size_usd = COALESCE(?, position_size_usd),
                    payload_json = ?
                WHERE decision_id = ?
                """,
                (
                    now,
                    action.get("scanner_stage"),
                    action.get("final_action"),
                    action.get("action_reason") or action.get("reason"),
                    action.get("paper_lane"),
                    self.safe_float(action.get("position_size_usd")),
                    json.dumps(payload, default=str),
                    decision_id,
                ),
            )
        return cursor.rowcount > 0

    def update_decision_result(self, decision_id, result):
        if not decision_id:
            return False
        result = result if isinstance(result, dict) else {}
        now = time.time()
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT payload_json FROM decision_records WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if not row:
                return False
            payload = self.parse_json(row["payload_json"], {})
            payload["result"] = result
            cursor = conn.execute(
                """
                UPDATE decision_records
                SET updated_at = ?,
                    trade_id = COALESCE(?, trade_id),
                    trade_status = COALESCE(?, trade_status),
                    entry_time = COALESCE(?, entry_time),
                    close_time = COALESCE(?, close_time),
                    pnl = COALESCE(?, pnl),
                    pnl_pct = COALESCE(?, pnl_pct),
                    payload_json = ?,
                    result_json = ?
                WHERE decision_id = ?
                """,
                (
                    now,
                    result.get("trade_id"),
                    result.get("trade_status") or result.get("status"),
                    self.safe_float(result.get("entry_time")),
                    self.safe_float(result.get("close_time")),
                    self.safe_float(result.get("pnl")),
                    self.safe_float(result.get("pnl_pct")),
                    json.dumps(payload, default=str),
                    json.dumps(result, default=str),
                    decision_id,
                ),
            )
        return cursor.rowcount > 0

    def counts(self):
        with self.connect() as conn:
            return {
                "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                "alerts": conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0],
                "trades": conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0],
                "watchlist": conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0],
                "token_snapshots": conn.execute("SELECT COUNT(*) FROM token_snapshots").fetchone()[0],
                "swap_ticks": conn.execute("SELECT COUNT(*) FROM swap_ticks").fetchone()[0],
                "decision_records": conn.execute("SELECT COUNT(*) FROM decision_records").fetchone()[0],
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
                SELECT mint, wallet, status, risk_level, updated_at
                FROM watchlist
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_token_snapshots(self, limit=25):
        limit = self.safe_limit(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT time, mint, source, context, price, liquidity, risk_label
                FROM token_snapshots
                ORDER BY time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_swap_ticks(self, mint=None, limit=300, newest_first=True):
        limit = self.safe_limit(limit, default=300, maximum=1000)
        where = ""
        params = []
        if mint:
            where = "WHERE mint = ?"
            params.append(mint)
        params.append(limit)
        direction = "DESC" if newest_first else "ASC"
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT time, mint, signature, wallet, side, price, market_cap,
                       liquidity, token_amount, sol_amount, source, payload_json
                FROM swap_ticks
                {where}
                ORDER BY time {direction}, id {direction}
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_decisions(self, limit=50, mint=None):
        limit = self.safe_limit(limit, default=50, maximum=500)
        where = ""
        params = []
        if mint:
            where = "WHERE mint = ?"
            params.append(mint)
        params.append(limit)
        with self.connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT decision_id, created_at, updated_at, mint, signal_type,
                       scanner_stage, final_action, action_reason, paper_lane,
                       should_trade, total_score, threshold, edge_score,
                       edge_verdict, risk_label, risk_score, buy_quote_pass,
                       sell_quote_pass, position_size_usd, trade_id,
                       trade_status, entry_time, close_time, pnl, pnl_pct,
                       payload_json, result_json
                FROM decision_records
                {where}
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        decisions = []
        for row in rows:
            item = dict(row)
            item["should_trade"] = bool(item["should_trade"])
            item["buy_quote_pass"] = self.bool_from_db(item["buy_quote_pass"])
            item["sell_quote_pass"] = self.bool_from_db(item["sell_quote_pass"])
            item["payload"] = self.parse_json(item.pop("payload_json"), {})
            item["result"] = self.parse_json(item.pop("result_json"), None)
            decisions.append(item)
        return decisions

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

    def safe_bool_int(self, value):
        if value is None:
            return None
        return 1 if bool(value) else 0

    def bool_from_db(self, value):
        if value is None:
            return None
        return bool(value)

    def parse_json(self, value, default):
        try:
            if value in [None, ""]:
                return default
            return json.loads(value)
        except Exception:
            return default

    def safe_limit(self, value, default=25, maximum=250):
        try:
            value = int(value)
        except Exception:
            value = default
        return max(1, min(maximum, value))
