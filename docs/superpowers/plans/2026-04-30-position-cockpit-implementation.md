# Position Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Axiom-style Position Cockpit inside the current Streamlit dashboard with live-looking monitoring and simulation-only action controls.

**Architecture:** Add focused core services for position cockpit state, candle aggregation, and simulated action intents, then render that state from a new dashboard section. Use existing JSON/SQLite sources and avoid adding live execution paths.

**Tech Stack:** Python, Streamlit, SQLite via `core/storage.py`, existing JSON state files, `unittest`.

---

## File Structure

- Create `core/position_cockpit.py`: pure builders for selected positions, candle bars, metrics, tabs, and action intents.
- Modify `dashboard/dashboard.py`: render the Axiom-style Position Cockpit section and wire safe buttons.
- Modify `tests/test_core_logic.py`: add unit tests for candle generation and simulated action intent creation.
- Modify `WORK_LOG.md`: record completed implementation and verification.
- Modify `research/BUILD_PLAN.md`: mark Position Cockpit as started/usable in current Streamlit cockpit.
- Modify `research/DATA_SOURCE_MAP.md`: document cockpit sources and new simulated action intent file.

## Task 1: Position Cockpit Core Model

**Files:**
- Create: `core/position_cockpit.py`
- Test: `tests/test_core_logic.py`

- [ ] **Step 1: Add failing tests for candle and action builders**

Add these tests to `tests/test_core_logic.py`:

```python
from core.position_cockpit import build_candles, build_simulated_action_intent


class PositionCockpitTests(unittest.TestCase):
    def test_build_candles_groups_snapshots(self):
        candles = build_candles([
            {"time": 100, "price": 1.0, "market_cap": 1000},
            {"time": 101, "price": 1.2, "market_cap": 1200},
            {"time": 106, "price": 0.9, "market_cap": 900},
        ], interval_seconds=5)

        self.assertEqual(len(candles), 2)
        self.assertEqual(candles[0]["open"], 1.0)
        self.assertEqual(candles[0]["close"], 1.2)
        self.assertEqual(candles[0]["high"], 1.2)
        self.assertEqual(candles[0]["low"], 1.0)
        self.assertEqual(candles[0]["color"], "green")
        self.assertEqual(candles[1]["color"], "red")

    def test_simulated_action_intent_is_never_live(self):
        intent = build_simulated_action_intent(
            mint="Mint111",
            action_type="prepare_exit_early",
            source="position_cockpit",
            amount={"sell_pct": 100},
            reason="operator_pressed_exit_early",
        )

        self.assertEqual(intent["mint"], "Mint111")
        self.assertEqual(intent["action_type"], "prepare_exit_early")
        self.assertEqual(intent["execution_mode"], "SIMULATION_ONLY")
        self.assertFalse(intent["live_action_allowed"])
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python3 -m unittest tests.test_core_logic
```

Expected: import failure for `core.position_cockpit`.

- [ ] **Step 3: Implement pure core builders**

Create `core/position_cockpit.py`:

```python
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.json_store import locked_update_json, read_json


ACTION_INTENTS_FILE = Path("data/position_action_intents.json")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_float(value, default=0):
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


def normalize_mint(value):
    return str(value or "").strip()


def position_mint(position):
    if not isinstance(position, dict):
        return ""
    return normalize_mint(position.get("mint") or position.get("token_mint"))


def build_position_rows(paper_state, watchlist):
    rows = []
    for trade in paper_state.get("open_trades", []) if isinstance(paper_state, dict) else []:
        if not isinstance(trade, dict):
            continue
        mint = position_mint(trade)
        if not mint:
            continue
        rows.append({
            "source": "paper_trade",
            "mint": mint,
            "label": trade.get("symbol") or trade.get("name") or mint[:8],
            "status": trade.get("status", "open"),
            "entry_price": safe_float(trade.get("entry_price")),
            "current_price": safe_float(trade.get("current_price"), safe_float(trade.get("entry_price"))),
            "entry_market_cap": trade.get("entry_market_cap"),
            "current_market_cap": trade.get("current_market_cap") or trade.get("market_cap"),
            "liquidity": trade.get("current_liquidity_usd") or trade.get("liquidity_usd"),
            "size_usd": trade.get("size_usd"),
            "remaining_pct": trade.get("remaining_pct"),
            "total_pnl": trade.get("total_pnl"),
            "total_pnl_pct": trade.get("total_pnl_pct"),
            "raw": trade,
        })

    watched = {position_mint(row) for row in rows}
    for item in watchlist if isinstance(watchlist, list) else []:
        if not isinstance(item, dict):
            continue
        mint = position_mint(item)
        if not mint or mint in watched:
            continue
        rows.append({
            "source": "manual_watchlist",
            "mint": mint,
            "label": item.get("symbol") or item.get("name") or mint[:8],
            "status": item.get("status", "WATCHING"),
            "current_price": safe_float(item.get("current_price")),
            "current_market_cap": item.get("market_cap"),
            "liquidity": item.get("current_liquidity"),
            "risk_level": item.get("risk_level"),
            "alert_level": item.get("alert_level"),
            "holder_count": item.get("holder_count"),
            "raw": item,
        })
    return rows


def build_candles(snapshots, interval_seconds=5, value_key="price"):
    grouped = defaultdict(list)
    interval = max(1, int(interval_seconds or 5))
    for snapshot in snapshots or []:
        if not isinstance(snapshot, dict):
            continue
        ts = safe_float(snapshot.get("time") or snapshot.get("timestamp"))
        value = safe_float(snapshot.get(value_key))
        if value <= 0 and value_key != "market_cap":
            value = safe_float(snapshot.get("market_cap"))
        if ts <= 0 or value <= 0:
            continue
        bucket = int(ts // interval) * interval
        grouped[bucket].append((ts, value))

    candles = []
    for bucket in sorted(grouped):
        points = sorted(grouped[bucket], key=lambda item: item[0])
        values = [point[1] for point in points]
        open_value = values[0]
        close_value = values[-1]
        candles.append({
            "time": bucket,
            "time_iso": datetime.fromtimestamp(bucket, tz=timezone.utc).isoformat(),
            "open": open_value,
            "high": max(values),
            "low": min(values),
            "close": close_value,
            "volume": len(values),
            "color": "green" if close_value >= open_value else "red",
        })
    return candles[-120:]


def build_simulated_action_intent(mint, action_type, source, amount=None, reason="operator_request"):
    return {
        "id": f"{normalize_mint(mint)}:{action_type}:{int(time.time() * 1000)}",
        "time": time.time(),
        "created_at": utc_now(),
        "mint": normalize_mint(mint),
        "action_type": action_type,
        "source": source,
        "amount": amount or {},
        "reason": reason,
        "execution_mode": "SIMULATION_ONLY",
        "live_action_allowed": False,
        "status": "prepared",
        "safety_note": "Prepared action only. No live buy or sell was executed.",
    }


def record_simulated_action_intent(intent, path=ACTION_INTENTS_FILE):
    def updater(data):
        if not isinstance(data, dict):
            data = {"intents": []}
        intents = data.get("intents", [])
        if not isinstance(intents, list):
            intents = []
        intents.insert(0, intent)
        data["intents"] = intents[:500]
        data["last_updated"] = time.time()
        return data

    return locked_update_json(path, {"intents": []}, updater)


def load_action_intents(path=ACTION_INTENTS_FILE):
    data = read_json(path, {"intents": []})
    return data if isinstance(data, dict) else {"intents": []}
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
python3 -m unittest tests.test_core_logic
```

Expected: all tests pass.

## Task 2: Dashboard Position Cockpit Renderer

**Files:**
- Modify: `dashboard/dashboard.py`

- [ ] **Step 1: Import cockpit helpers**

Add:

```python
from core.position_cockpit import (
    build_candles,
    build_position_rows,
    build_simulated_action_intent,
    load_action_intents,
    record_simulated_action_intent,
)
```

- [ ] **Step 2: Add snapshot helper**

Add a helper near the existing dashboard helpers:

```python
def token_snapshots_for_mint(store, mint, limit=250):
    if not mint:
        return []
    try:
        with store.connect() as conn:
            conn.row_factory = None
            rows = conn.execute(
                """
                SELECT time, mint, source, context, price, liquidity, risk_label, payload_json
                FROM token_snapshots
                WHERE mint = ?
                ORDER BY time DESC, id DESC
                LIMIT ?
                """,
                (mint, int(limit)),
            ).fetchall()
    except Exception:
        return []

    snapshots = []
    for row in rows:
        time_value, mint_value, source, context, price, liquidity, risk_label, payload_json = row
        try:
            payload = json.loads(payload_json or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload.setdefault("time", time_value)
        payload.setdefault("mint", mint_value)
        payload.setdefault("source", source)
        payload.setdefault("context", context)
        payload.setdefault("price", price)
        payload.setdefault("liquidity", liquidity)
        payload.setdefault("risk_label", risk_label)
        snapshots.append(payload)
    return list(reversed(snapshots))
```

- [ ] **Step 3: Add simple candle renderer**

Add:

```python
def render_candle_strip(candles):
    if not candles:
        st.info("No local price snapshots yet for this token.")
        return

    values = []
    for candle in candles:
        values.extend([candle["high"], candle["low"]])
    high = max(values)
    low = min(values)
    span = max(high - low, high * 0.01, 1e-12)

    bars = []
    for candle in candles[-80:]:
        top = 100 - ((candle["high"] - low) / span * 100)
        bottom = 100 - ((candle["low"] - low) / span * 100)
        body_top = 100 - ((max(candle["open"], candle["close"]) - low) / span * 100)
        body_bottom = 100 - ((min(candle["open"], candle["close"]) - low) / span * 100)
        color = "#22c55e" if candle["color"] == "green" else "#ef4444"
        bars.append(
            f"<div class='pc-candle'>"
            f"<span class='pc-wick' style='top:{top:.2f}%;height:{max(2, bottom-top):.2f}%;background:{color}'></span>"
            f"<span class='pc-body' style='top:{body_top:.2f}%;height:{max(3, body_bottom-body_top):.2f}%;background:{color}'></span>"
            f"</div>"
        )

    st.markdown(
        "<div class='pc-chart'>" + "".join(bars) + "</div>",
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Add Position Cockpit CSS and renderer**

Add a `render_position_cockpit(...)` function that:

- builds selectable positions from paper trades and manual watchlist,
- loads snapshots for selected mint,
- builds candles,
- renders header metrics,
- renders candle strip,
- renders right action panel,
- records simulation-only intents when buttons are pressed,
- renders bottom tabs.

Use unique Streamlit keys with the selected mint in the key.

- [ ] **Step 5: Place section before Open Trades**

Call:

```python
render_position_cockpit(paper_state, watchlist, store, runtime_status)
st.divider()
```

before the existing `st.header("📈 Open Trades")`.

- [ ] **Step 6: Compile dashboard**

Run:

```bash
python3 -m py_compile dashboard/dashboard.py core/position_cockpit.py
```

Expected: no output.

## Task 3: Docs And Verification

**Files:**
- Modify: `WORK_LOG.md`
- Modify: `research/BUILD_PLAN.md`
- Modify: `research/DATA_SOURCE_MAP.md`

- [ ] **Step 1: Update data source map**

Add `data/position_action_intents.json` as the simulation-only ledger for cockpit button actions.

- [ ] **Step 2: Update build plan**

Mark Position Cockpit as usable in the current Streamlit cockpit and note that the final pro GUI should use a richer stack.

- [ ] **Step 3: Update work log**

Add a completed work entry with changed files, behavior, verification, and remaining limitations.

- [ ] **Step 4: Run full verification**

Run:

```bash
python3 -m unittest discover
trading_env/bin/python -m unittest discover
trading_env/bin/python -m py_compile core/position_cockpit.py dashboard/dashboard.py tests/test_core_logic.py
curl -I --max-time 5 http://127.0.0.1:8501/
```

Expected:

- both unittest commands pass,
- py_compile has no output,
- curl returns `HTTP/1.1 200 OK`.

## Self-Review

- Spec coverage: the plan covers Axiom-style layout, data sources, candle-style chart, simulated exit/add actions, safety restrictions, and docs.
- Placeholder scan: no implementation step depends on undefined future work.
- Type consistency: all helper names are defined before dashboard integration.
