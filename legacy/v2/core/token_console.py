from datetime import datetime, timezone


def safe_float(value, default=0.0):
    try:
        if value in [None, ""]:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value in [None, ""]:
            return default
        return int(float(value))
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


def timestamp_value(value, default=0.0):
    if value in [None, ""]:
        return default

    numeric = safe_float(value, None)
    if numeric is not None:
        return numeric

    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            return default

    return default


def record_time(record):
    if not isinstance(record, dict):
        return 0.0
    return max(
        timestamp_value(record.get("timestamp")),
        timestamp_value(record.get("time")),
        timestamp_value(record.get("last_signal_time")),
        timestamp_value(record.get("last_updated")),
        timestamp_value(record.get("updated_at")),
        timestamp_value(record.get("last_update")),
        timestamp_value(record.get("entry_time")),
        timestamp_value(record.get("close_time")),
    )


class TokenConsole:
    """Aggregate token-level state for backend dashboards and reports."""

    RISK_ORDER = {
        "EMERGENCY": 5,
        "DANGER": 4,
        "HIGH_RISK": 4,
        "BLOCKED": 4,
        "WARNING": 3,
        "MEDIUM_RISK": 3,
        "UNKNOWN": 2,
        "LOW_RISK": 1,
        "SAFE": 0,
    }

    def build(self, live_state=None, paper_state=None, watchlist=None, candidate_ledger=None):
        live_state = live_state if isinstance(live_state, dict) else {}
        paper_state = paper_state if isinstance(paper_state, dict) else {}
        watchlist = watchlist if isinstance(watchlist, list) else []
        candidate_ledger = candidate_ledger if isinstance(candidate_ledger, dict) else {}

        records = {}
        self._merge_live_state(records, live_state)
        self._merge_trades(records, paper_state)
        self._merge_watchlist(records, watchlist)
        self._merge_candidate_ledger(records, candidate_ledger)

        for mint, record in records.items():
            record["mint"] = mint
            record["latest_alert"] = self.latest_alert(record.get("alerts", []))
            record["trade_stats"] = self.trade_stats(record.get("trades", []))
            record["protection"] = self.protection_status(record.get("watchlist_item"))
            record["ledger"] = self.ledger_status(record.get("ledger_item"))
            record["market"] = self.market_info(record)
            record["signal"] = self.signal_fields(record)
            record["risk"] = self.risk_fields(record)
            record["edge"] = self.edge_fields(record)
            record["recommended_action"] = self.recommended_action(record)
            record["sort"] = self.sort_fields(record)

        return records

    def rows(self, live_state=None, paper_state=None, watchlist=None, candidate_ledger=None, limit=None):
        records = self.build(live_state, paper_state, watchlist, candidate_ledger)
        rows = [self.row(record) for record in records.values()]
        rows.sort(
            key=lambda row: (
                row.get("has_open_trade") is True,
                row.get("protected") is True,
                row.get("edge_score") or 0,
                row.get("latest_time") or 0,
                row.get("liquidity") or 0,
            ),
            reverse=True,
        )
        if limit is not None:
            return rows[:safe_int(limit, len(rows))]
        return rows

    def row(self, record):
        market = record.get("market") or {}
        stats = record.get("trade_stats") or {}
        protection = record.get("protection") or {}
        ledger = record.get("ledger") or {}
        edge = record.get("edge") or {}
        risk = record.get("risk") or {}
        signal = record.get("signal") or {}

        return {
            "mint": record.get("mint"),
            "name": market.get("name"),
            "symbol": market.get("symbol"),
            "url": market.get("url"),
            "liquidity": market.get("liquidity"),
            "volume": market.get("volume"),
            "price": market.get("price"),
            "latest_time": (record.get("sort") or {}).get("latest_time"),
            "signal_type": signal.get("type"),
            "wallet_count": signal.get("wallet_count"),
            "weighted_wallet_score": signal.get("weighted_wallet_score"),
            "score": signal.get("total_score"),
            "edge_score": edge.get("score"),
            "edge_verdict": edge.get("verdict"),
            "quote_worthy": edge.get("quote_worthy"),
            "paper_trade_worthy": edge.get("paper_trade_worthy"),
            "risk_label": risk.get("label"),
            "risk_score": risk.get("score"),
            "risk_warnings": risk.get("warnings"),
            "token_standard": risk.get("token_standard"),
            "token_mechanics_risk": risk.get("token_mechanics_risk"),
            "token_extensions": risk.get("token_extensions"),
            "protected": protection.get("protected"),
            "protection_status": protection.get("status"),
            "watchlist_risk": protection.get("risk_level"),
            "ledger_status": ledger.get("status"),
            "ledger_note": ledger.get("note"),
            "has_open_trade": stats.get("has_open_trade"),
            "open_trades": stats.get("open_count"),
            "closed_trades": stats.get("closed_count"),
            "total_pnl": stats.get("total_pnl"),
            "total_pnl_pct": stats.get("latest_pnl_pct"),
            "recommended_action": record.get("recommended_action"),
        }

    def latest_alert(self, alerts):
        valid = [alert for alert in alerts if isinstance(alert, dict)]
        if not valid:
            return {}
        return max(valid, key=record_time)

    def trade_stats(self, trades):
        valid = [trade for trade in trades if isinstance(trade, dict)]
        open_trades = [t for t in valid if str(t.get("status", "")).lower() == "open"]
        closed_trades = [t for t in valid if str(t.get("status", "")).lower() == "closed"]
        latest = max(valid, key=record_time) if valid else {}
        total_pnl = sum(safe_float(first_present(t, ["total_pnl", "pnl", "realized_pnl"])) for t in valid)
        pnl_values = [safe_float(first_present(t, ["total_pnl", "pnl", "realized_pnl"])) for t in valid]

        return {
            "count": len(valid),
            "open_count": len(open_trades),
            "closed_count": len(closed_trades),
            "has_open_trade": bool(open_trades),
            "total_pnl": round(total_pnl, 6),
            "best_pnl": max(pnl_values) if pnl_values else 0.0,
            "worst_pnl": min(pnl_values) if pnl_values else 0.0,
            "latest_pnl": safe_float(first_present(latest, ["total_pnl", "pnl", "unrealized_pnl"])),
            "latest_pnl_pct": safe_float(first_present(latest, ["total_pnl_pct", "pnl_pct"])),
            "latest_status": latest.get("status"),
            "latest_trade": latest,
            "open_trade": max(open_trades, key=record_time) if open_trades else {},
        }

    def protection_status(self, item):
        if not isinstance(item, dict) or not item:
            return {
                "protected": False,
                "status": "UNPROTECTED",
                "risk_level": "UNKNOWN",
                "alert_only": False,
                "auto_sell": False,
                "reason": None,
            }

        return {
            "protected": True,
            "status": item.get("status") or "PROTECTED",
            "risk_level": item.get("risk_level") or item.get("status") or "UNKNOWN",
            "alert_only": bool(item.get("alert_only")),
            "auto_sell": bool(item.get("auto_sell")),
            "reason": item.get("reason"),
            "last_update": item.get("last_update") or item.get("updated_at") or item.get("created_at"),
        }

    def ledger_status(self, item):
        if not isinstance(item, dict) or not item:
            return {
                "present": False,
                "status": None,
                "note": None,
                "updated_at": None,
            }
        return {
            "present": True,
            "status": item.get("status"),
            "note": item.get("note"),
            "updated_at": item.get("updated_at"),
            "last_edge_score": item.get("last_edge_score"),
            "last_edge_verdict": item.get("last_edge_verdict"),
            "last_score": item.get("last_score"),
            "last_risk": item.get("last_risk"),
        }

    def edge_fields(self, record):
        source = self._best_signal_source(record)
        ledger = record.get("ledger_item") or {}
        return {
            "score": safe_float(first_present(source, ["edge_score"], ledger.get("last_edge_score")), None),
            "verdict": first_present(source, ["edge_verdict"], ledger.get("last_edge_verdict")),
            "quote_worthy": bool(first_present(source, ["edge_quote_worthy", "quote_worthy"], False)),
            "paper_trade_worthy": bool(first_present(source, ["edge_paper_trade_worthy", "paper_trade_worthy"], False)),
            "positives": first_present(source, ["edge_positives", "positives"], []),
            "risks": first_present(source, ["edge_risks", "risks"], []),
        }

    def risk_fields(self, record):
        source = self._best_signal_source(record)
        watch = record.get("watchlist_item") or {}
        ledger = record.get("ledger_item") or {}
        label = first_present(
            source,
            ["risk_label", "risk_level"],
            first_present(watch, ["risk_level", "status"], ledger.get("last_risk") or "UNKNOWN"),
        )
        return {
            "label": label,
            "score": safe_float(first_present(source, ["risk_score"]), None),
            "warnings": first_present(source, ["risk_warnings", "warnings"], []),
            "hard_block": bool(first_present(source, ["hard_block"], False)),
            "hard_block_reason": first_present(source, ["hard_block_reason"]),
            "watchlist_risk": watch.get("risk_level"),
            "token_standard": first_present(source, ["token_standard"]),
            "token_mechanics_risk": first_present(source, ["token_mechanics_risk"]),
            "token_extensions": first_present(source, ["token_extensions"], []),
            "token_mechanics_reasons": first_present(source, ["token_mechanics_reasons"], []),
        }

    def signal_fields(self, record):
        source = self._best_signal_source(record)
        ledger = record.get("ledger_item") or {}
        return {
            "type": first_present(source, ["type", "signal_type"]),
            "wallet_count": safe_int(first_present(source, ["wallet_count"]), None),
            "weighted_wallet_score": safe_float(first_present(source, ["weighted_wallet_score"]), None),
            "total_score": safe_float(first_present(source, ["total_score"], ledger.get("last_score")), None),
            "should_trade": bool(first_present(source, ["should_trade"], False)),
            "strategy_guard_action": first_present(source, ["strategy_guard_action"]),
            "strategy_guard_reason": first_present(source, ["strategy_guard_reason"]),
            "last_signal_time": first_present(source, ["timestamp", "time", "last_signal_time"]),
        }

    def market_info(self, record):
        sources = [
            record.get("latest_alert"),
            record.get("latest_token"),
            record.get("watchlist_item"),
            (record.get("trade_stats") or {}).get("open_trade"),
            (record.get("trade_stats") or {}).get("latest_trade"),
        ]
        market = {}
        for source in sources:
            if not isinstance(source, dict):
                continue
            nested = source.get("market_info") if isinstance(source.get("market_info"), dict) else {}
            market = self._fill_market(market, nested)
            market = self._fill_market(market, source)
        return market

    def recommended_action(self, record):
        stats = record.get("trade_stats") or {}
        protection = record.get("protection") or {}
        ledger = record.get("ledger") or {}
        edge = record.get("edge") or {}
        risk = record.get("risk") or {}

        risk_label = str(risk.get("label") or "UNKNOWN")
        ledger_status = str(ledger.get("status") or "")
        edge_score = safe_float(edge.get("score"))

        if stats.get("has_open_trade"):
            if self.RISK_ORDER.get(risk_label, 2) >= 4 or risk.get("hard_block"):
                return "REVIEW_EXIT"
            return "MONITOR_POSITION"

        if protection.get("protected"):
            if self.RISK_ORDER.get(risk_label, 2) >= 4:
                return "PROTECTION_ALERT"
            return "WATCH_PROTECTED"

        if ledger_status == "IGNORED":
            return "IGNORE"

        if ledger_status == "PROTECTED":
            return "VERIFY_PROTECTION"

        if self.RISK_ORDER.get(risk_label, 2) >= 4 or risk.get("hard_block"):
            return "AVOID"

        if edge.get("paper_trade_worthy") or edge_score >= 62:
            return "CONSIDER_PAPER_TRADE"

        if edge.get("quote_worthy") or edge_score >= 45:
            return "QUOTE_CHECK"

        if edge_score >= 28 or edge.get("verdict") == "WATCHLIST":
            return "WATCH"

        return "REVIEW"

    def sort_fields(self, record):
        times = [
            record_time(record.get("latest_alert")),
            record_time(record.get("latest_token")),
            record_time(record.get("watchlist_item")),
            record_time(record.get("ledger_item")),
            record_time((record.get("trade_stats") or {}).get("latest_trade")),
        ]
        return {
            "latest_time": max(times),
            "risk_rank": self.RISK_ORDER.get(str((record.get("risk") or {}).get("label")), 2),
            "edge_score": safe_float((record.get("edge") or {}).get("score")),
        }

    def _merge_live_state(self, records, live_state):
        for alert in live_state.get("alerts", []) or []:
            if not isinstance(alert, dict):
                continue
            mint = alert.get("mint") or alert.get("token_mint")
            if mint:
                self._record(records, mint).setdefault("alerts", []).append(alert)

        for token_group in [live_state.get("tokens") or {}, live_state.get("latest_tokens") or {}]:
            if not isinstance(token_group, dict):
                continue
            for mint, token in token_group.items():
                if not isinstance(token, dict):
                    continue
                actual_mint = token.get("mint") or token.get("token_mint") or mint
                record = self._record(records, actual_mint)
                current = record.get("latest_token")
                if not current or record_time(token) >= record_time(current):
                    record["latest_token"] = token

    def _merge_trades(self, records, paper_state):
        for key in ["open_trades", "closed_trades"]:
            for trade in paper_state.get(key, []) or []:
                if not isinstance(trade, dict):
                    continue
                mint = trade.get("mint") or trade.get("token_mint")
                if mint:
                    self._record(records, mint).setdefault("trades", []).append(trade)

    def _merge_watchlist(self, records, watchlist):
        for item in watchlist:
            if not isinstance(item, dict):
                continue
            mint = item.get("token_mint") or item.get("mint")
            if mint:
                self._record(records, mint)["watchlist_item"] = item

    def _merge_candidate_ledger(self, records, candidate_ledger):
        for mint, item in candidate_ledger.items():
            if mint and isinstance(item, dict):
                self._record(records, mint)["ledger_item"] = item

    def _record(self, records, mint):
        return records.setdefault(
            mint,
            {
                "alerts": [],
                "trades": [],
                "latest_token": {},
                "watchlist_item": {},
                "ledger_item": {},
            },
        )

    def _best_signal_source(self, record):
        return record.get("latest_alert") or record.get("latest_token") or {}

    def _fill_market(self, market, source):
        mapping = {
            "liquidity": ["liquidity", "liquidity_usd", "current_liquidity", "current_liquidity_usd"],
            "volume": ["volume", "volume_usd", "volume_24h"],
            "price": ["price", "current_price", "entry_price"],
            "name": ["name"],
            "symbol": ["symbol"],
            "url": ["url"],
            "source": ["source", "market_source"],
        }

        for target, keys in mapping.items():
            if market.get(target) not in [None, ""]:
                continue
            value = first_present(source, keys)
            if value in [None, ""]:
                continue
            if target in ["liquidity", "volume", "price"]:
                market[target] = safe_float(value, None)
            else:
                market[target] = value
        return market
