# Wallet Quant Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refocus MemeTraderPro into a Quant Wallet Tracker with clean wallet metrics, tiering, reporting, reduced product noise, replayable signal contexts, and no-trade analysis.

**Architecture:** Freeze non-wallet product lanes at the roadmap/UI level first, then add a wallet quant report generator that composes existing wallet JSON and SQLite evidence into one reviewable artifact. Keep live execution locked and avoid deleting useful data paths until the wallet report replaces them.

**Tech Stack:** Python, SQLite, JSON runtime state, existing desktop API/React GUI, `unittest`.

---

## Current Execution Status

- [x] Task 1 roadmap refocus completed.
- [x] Task 2 wallet metric model completed.
- [x] Task 3 wallet quant report builder completed.
- [x] Task 4 desktop API wallet quant endpoint completed.
- [x] Task 5 Quant Wallet Tracker V2 context layer completed.
- [x] Task 6 replay visibility foundation completed.
- [ ] Task 7 freeze non-wallet navigation.
- [~] Task 8 final verification partially completed: Python tests, compile checks, JSON validation, TypeScript check, report builder, and live endpoint verification passed.

## V2 Addendum - Signal Context And Replay Visibility

**Purpose:** Make every wallet signal and no-trade decision more observable, explainable, and replayable before adding strategy complexity.

**Completed V2 files:**

- `wallets/wallet_metrics.py`
- `wallets/wallet_profiles.py`
- `wallets/wallet_relationships.py`
- `wallets/wallet_score.py`
- `core/signal_context.py`
- `core/replay_visibility.py`
- `analysis/signal_context_logger.py`
- `utils/build_replay_visibility_report.py`
- `tests/test_signal_context.py`
- `tests/test_replay_visibility.py`

**Completed V2 behavior:**

- Wallet quant rows include explicit behavioral profiles and data-completeness counts.
- Rejected scanner and Market Radar paths produce V2 signal contexts.
- Rejection rows now include richer context for later filter calibration.
- Replay visibility reports expose trigger, market, risk, execution assumptions, market regime, and replay notes.
- Live execution remains locked; all V2 outputs are review-only.

**Next V2 task:**

Wire `core.signal_context.build_signal_context` into successful paper entries and closed paper outcomes so passed, skipped, and entered candidates can be compared under one schema.

## File Structure

- Modify `research/BUILD_PLAN.md` to make Wallet Quant Tracker the active roadmap and freeze unrelated lanes.
- Modify `WORK_LOG.md` and `handoff.md` to record the strategic refocus.
- Modify `research/DATA_SOURCE_MAP.md` to add the wallet quant source contract.
- Create `core/wallet_quant.py` for metric aggregation and tier recommendation.
- Create `utils/build_wallet_quant_report.py` as a CLI report builder.
- Create `tests/test_wallet_quant.py` for deterministic wallet scoring tests.
- Later modify `desktop_api.py` and the Wallets tab to read `data/wallet_quant_report.json`.

## Task 1: Roadmap Refocus

**Files:**
- Modify: `research/BUILD_PLAN.md`
- Modify: `WORK_LOG.md`
- Modify: `handoff.md`

- [ ] **Step 1: Update active roadmap language**

Replace the active focus in `research/BUILD_PLAN.md` with:

```markdown
<mark>Active roadmap area: Quant Wallet Tracker V1.</mark>

<mark>Current focus: Build a private wallet intelligence system that discovers wallets from runners, tracks repeat behavior, creates paper-watch evidence, promotes useful wallets, demotes noisy wallets, and gives the operator clean data-evaluation views.</mark>
```

- [ ] **Step 2: Add frozen-lane note**

Add a roadmap section named `Frozen Until Wallet Edge Is Measured` listing chart polish, social automation, AI explanations, manual protection expansion, Market Radar as a separate strategy, marketing assets, and live execution wiring.

- [ ] **Step 3: Log the refocus**

Add a `2026-05-14 update - Quant Wallet Tracker refocus` entry to `WORK_LOG.md` with changed files, rationale, frozen lanes, and next steps.

- [ ] **Step 4: Update handoff**

Update `handoff.md` so the next agent sees Quant Wallet Tracker as the primary product and does not continue broad cockpit work.

- [ ] **Step 5: Verify docs changed cleanly**

Run:

```bash
git diff --check
```

Expected: no output and exit code `0`.

## Task 2: Wallet Metric Model

**Files:**
- Create: `core/wallet_quant.py`
- Create: `tests/test_wallet_quant.py`

- [ ] **Step 1: Add failing tests for tier recommendation**

Create `tests/test_wallet_quant.py`:

```python
import unittest

from core.wallet_quant import recommend_wallet_tier, wallet_quant_row


class WalletQuantTests(unittest.TestCase):
    def test_promotion_review_requires_sample_and_positive_evidence(self):
        row = wallet_quant_row(
            wallet="WalletA",
            performance={"paper_entries": 8, "wins": 6, "losses": 2, "total_pnl": 42.0},
            behavior={"labels": ["paper-profitable"], "rolling": {"30d": {"expectancy": 5.25}}},
            current_tier="paper_watch",
        )
        self.assertEqual(recommend_wallet_tier(row)["action"], "PROMOTION_REVIEW")

    def test_demote_negative_wallet_with_sample(self):
        row = wallet_quant_row(
            wallet="WalletB",
            performance={"paper_entries": 7, "wins": 1, "losses": 6, "total_pnl": -28.0},
            behavior={"labels": ["late-exit"], "rolling": {"30d": {"expectancy": -4.0}}},
            current_tier="trusted",
        )
        self.assertEqual(recommend_wallet_tier(row)["action"], "DEMOTION_REVIEW")

    def test_hold_low_sample_wallet(self):
        row = wallet_quant_row(
            wallet="WalletC",
            performance={"paper_entries": 1, "wins": 1, "losses": 0, "total_pnl": 80.0},
            behavior={"labels": ["paper-profitable"]},
            current_tier="candidate",
        )
        self.assertEqual(recommend_wallet_tier(row)["action"], "HOLD_MORE_DATA")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to confirm it fails**

Run:

```bash
./trading_env/bin/python -m unittest tests.test_wallet_quant
```

Expected: import failure because `core.wallet_quant` does not exist.

- [ ] **Step 3: Implement wallet quant row and recommendation**

Create `core/wallet_quant.py`:

```python
from __future__ import annotations

from typing import Any


PROMOTION_MIN_ENTRIES = 6
PROMOTION_MIN_WIN_RATE = 55.0
DEMOTION_MIN_ENTRIES = 5


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if number == number else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def wallet_quant_row(wallet: str, performance: dict[str, Any] | None = None, behavior: dict[str, Any] | None = None, current_tier: str = "candidate") -> dict[str, Any]:
    performance = performance or {}
    behavior = behavior or {}
    entries = safe_int(performance.get("paper_entries") or performance.get("trades") or 0)
    wins = safe_int(performance.get("wins") or 0)
    losses = safe_int(performance.get("losses") or 0)
    total_pnl = safe_float(performance.get("total_pnl") or performance.get("pnl") or 0.0)
    win_rate = (wins / entries * 100.0) if entries else 0.0
    labels = behavior.get("labels") if isinstance(behavior.get("labels"), list) else []
    rolling = behavior.get("rolling") if isinstance(behavior.get("rolling"), dict) else {}
    rolling_30d = rolling.get("30d") if isinstance(rolling.get("30d"), dict) else {}
    expectancy = safe_float(rolling_30d.get("expectancy"), total_pnl / entries if entries else 0.0)
    row = {
        "wallet": wallet,
        "tier": current_tier,
        "paper_watch_entries": entries,
        "paper_watch_closed": wins + losses,
        "paper_watch_win_rate": round(win_rate, 2),
        "paper_watch_total_pnl": round(total_pnl, 6),
        "paper_watch_expectancy": round(expectancy, 6),
        "labels": [str(label) for label in labels],
    }
    row["recommendation"] = recommend_wallet_tier(row)
    return row


def recommend_wallet_tier(row: dict[str, Any]) -> dict[str, Any]:
    entries = safe_int(row.get("paper_watch_entries"))
    win_rate = safe_float(row.get("paper_watch_win_rate"))
    total_pnl = safe_float(row.get("paper_watch_total_pnl"))
    expectancy = safe_float(row.get("paper_watch_expectancy"))
    tier = str(row.get("tier") or "candidate")
    reasons: list[str] = []
    if entries < DEMOTION_MIN_ENTRIES:
        return {"action": "HOLD_MORE_DATA", "reasons": [f"sample below {DEMOTION_MIN_ENTRIES} entries"]}
    if total_pnl < 0 and expectancy < 0:
        return {"action": "DEMOTION_REVIEW", "reasons": ["negative total pnl", "negative expectancy"]}
    if entries >= PROMOTION_MIN_ENTRIES and win_rate >= PROMOTION_MIN_WIN_RATE and total_pnl > 0 and expectancy > 0:
        reasons.extend(["sample threshold met", "positive total pnl", "positive expectancy", f"win rate {win_rate:.1f}%"])
        return {"action": "PROMOTION_REVIEW" if tier != "trusted" else "KEEP_TRUSTED", "reasons": reasons}
    return {"action": "HOLD_MORE_DATA", "reasons": ["evidence not strong enough for promotion or demotion"]}
```

- [ ] **Step 4: Run test to confirm it passes**

Run:

```bash
./trading_env/bin/python -m unittest tests.test_wallet_quant
```

Expected: `Ran 3 tests ... OK`.

## Task 3: Wallet Quant Report Builder

**Files:**
- Modify: `core/wallet_quant.py`
- Create: `utils/build_wallet_quant_report.py`
- Modify: `tests/test_wallet_quant.py`
- Modify: `research/DATA_SOURCE_MAP.md`

- [ ] **Step 1: Add report test**

Append to `tests/test_wallet_quant.py`:

```python
    def test_build_report_groups_wallets_by_recommendation(self):
        report = build_wallet_quant_report(
            tracked_wallets=["TrustedA"],
            paper_watch_wallets=["WalletA", "WalletB"],
            performance={
                "wallets": {
                    "WalletA": {"paper_entries": 8, "wins": 6, "losses": 2, "total_pnl": 42.0},
                    "WalletB": {"paper_entries": 7, "wins": 1, "losses": 6, "total_pnl": -28.0},
                }
            },
            behavior={"wallets": {"WalletA": {"rolling": {"30d": {"expectancy": 5.25}}}, "WalletB": {"rolling": {"30d": {"expectancy": -4.0}}}}},
        )
        self.assertEqual(report["counts"]["paper_watch"], 2)
        self.assertEqual(report["recommendation_counts"]["PROMOTION_REVIEW"], 1)
        self.assertEqual(report["recommendation_counts"]["DEMOTION_REVIEW"], 1)
```

Also update the import:

```python
from core.wallet_quant import build_wallet_quant_report, recommend_wallet_tier, wallet_quant_row
```

- [ ] **Step 2: Implement report grouping**

Add to `core/wallet_quant.py`:

```python
import time


def normalize_wallet_list(value: Any) -> list[str]:
    if isinstance(value, dict):
        value = value.get("wallets") or value.get("items") or []
    if not isinstance(value, list):
        return []
    wallets: list[str] = []
    seen: set[str] = set()
    for item in value:
        wallet = item.get("wallet") if isinstance(item, dict) else item
        wallet = str(wallet or "").strip()
        if wallet and wallet not in seen:
            wallets.append(wallet)
            seen.add(wallet)
    return wallets


def build_wallet_quant_report(tracked_wallets: Any, paper_watch_wallets: Any, performance: dict[str, Any], behavior: dict[str, Any]) -> dict[str, Any]:
    tracked = set(normalize_wallet_list(tracked_wallets))
    paper_watch = set(normalize_wallet_list(paper_watch_wallets))
    performance_wallets = performance.get("wallets") if isinstance(performance.get("wallets"), dict) else {}
    behavior_wallets = behavior.get("wallets") if isinstance(behavior.get("wallets"), dict) else {}
    all_wallets = sorted(tracked | paper_watch | set(performance_wallets) | set(behavior_wallets))
    rows = []
    recommendation_counts: dict[str, int] = {}
    for wallet in all_wallets:
        tier = "trusted" if wallet in tracked else "paper_watch" if wallet in paper_watch else "candidate"
        row = wallet_quant_row(
            wallet=wallet,
            performance=performance_wallets.get(wallet) if isinstance(performance_wallets.get(wallet), dict) else {},
            behavior=behavior_wallets.get(wallet) if isinstance(behavior_wallets.get(wallet), dict) else {},
            current_tier=tier,
        )
        action = row["recommendation"]["action"]
        recommendation_counts[action] = recommendation_counts.get(action, 0) + 1
        rows.append(row)
    rows.sort(key=lambda item: (item["recommendation"]["action"] == "PROMOTION_REVIEW", item["paper_watch_expectancy"], item["paper_watch_entries"]), reverse=True)
    return {
        "generated_at": time.time(),
        "mode": "WALLET_QUANT_REVIEW_ONLY",
        "live_execution_locked": True,
        "counts": {
            "wallets": len(rows),
            "trusted": len(tracked),
            "paper_watch": len(paper_watch),
        },
        "recommendation_counts": recommendation_counts,
        "wallets": rows,
    }
```

- [ ] **Step 3: Create CLI writer**

Create `utils/build_wallet_quant_report.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from core.wallet_quant import build_wallet_quant_report

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return default


def main() -> int:
    report = build_wallet_quant_report(
        tracked_wallets=read_json(ROOT / "data" / "tracked_wallets.json", []),
        paper_watch_wallets=read_json(ROOT / "data" / "paper_watch_wallets.json", {"wallets": []}),
        performance=read_json(ROOT / "data" / "wallet_performance.json", {"wallets": {}}),
        behavior=read_json(ROOT / "data" / "wallet_behavior.json", {"wallets": {}}),
    )
    out = ROOT / "data" / "wallet_quant_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(f"wrote {out.relative_to(ROOT)} wallets={report['counts']['wallets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and report builder**

Run:

```bash
./trading_env/bin/python -m unittest tests.test_wallet_quant
./trading_env/bin/python utils/build_wallet_quant_report.py
```

Expected: tests pass and command prints `wrote data/wallet_quant_report.json wallets=...`.

## Task 4: Desktop API Wallet Quant Endpoint

**Files:**
- Modify: `desktop_api.py`
- Modify: `tests/test_desktop_api.py`
- Modify: `research/DATA_SOURCE_MAP.md`

- [ ] **Step 1: Add endpoint test**

Add a desktop API test that calls the route handler for `/api/wallet-quant` and verifies:

```python
self.assertTrue(payload["live_execution_locked"])
self.assertEqual(payload["mode"], "WALLET_QUANT_REVIEW_ONLY")
self.assertIn("wallets", payload)
self.assertIn("recommendation_counts", payload)
```

- [ ] **Step 2: Add payload builder**

In `desktop_api.py`, import:

```python
from core.wallet_quant import build_wallet_quant_report
```

Add:

```python
def build_wallet_quant_payload(state=None):
    state = state or read_state_files()
    return build_wallet_quant_report(
        tracked_wallets=state.get("tracked_wallets", []),
        paper_watch_wallets=state.get("paper_watch_wallets", {"wallets": []}),
        performance=state.get("wallet_performance") if isinstance(state.get("wallet_performance"), dict) else {"wallets": {}},
        behavior=state.get("wallet_behavior") if isinstance(state.get("wallet_behavior"), dict) else {"wallets": {}},
    )
```

- [ ] **Step 3: Add route**

In the GET route block, add:

```python
if path == "/api/wallet-quant":
    return json_response(build_wallet_quant_payload())
```

- [ ] **Step 4: Verify desktop API tests**

Run:

```bash
./trading_env/bin/python -m unittest tests.test_desktop_api
```

Expected: all desktop API tests pass.

## Task 5: Freeze Non-Wallet Navigation

**Files:**
- Modify: `apps/desktop/src/App.tsx`
- Modify: existing React tests as needed.

- [ ] **Step 1: Identify visible tabs**

Find the tab definition in `apps/desktop/src/App.tsx`.

- [ ] **Step 2: Keep only evaluation-first tabs active**

For the next iteration, keep:

- Portfolio or Results.
- Wallets.
- System.

Move or label these as frozen:

- Cockpit.
- Social / Catalysts.
- Protection.
- Replay unless used for wallet-decision lineage.

- [ ] **Step 3: Add clear frozen copy**

Display:

```text
Frozen while Quant Wallet Tracker V1 is being built.
```

No trading promise, no live execution copy.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
npm --prefix apps/desktop run check
npm --prefix apps/desktop test -- --run
```

Expected: TypeScript and React tests pass.

## Task 6: Final Verification

**Files:**
- All changed files.

- [ ] **Step 1: Run Python checks**

Run:

```bash
./trading_env/bin/python -m unittest tests.test_core_logic tests.test_desktop_api tests.test_market_checker tests.test_wallet_quant
```

Expected: all tests pass.

- [ ] **Step 2: Run compile and JSON checks**

Run:

```bash
find . -path './trading_env' -prune -o -path './.git' -prune -o -path './apps/desktop/node_modules' -prune -o -path './apps/desktop/src-tauri/target' -prune -o -name '*.py' -print0 | xargs -0 ./trading_env/bin/python -m py_compile
./trading_env/bin/python -m json.tool data/wallet_quant_report.json >/dev/null
```

Expected: both commands exit `0`.

- [ ] **Step 3: Run frontend checks**

Run:

```bash
npm --prefix apps/desktop run check
npm --prefix apps/desktop test -- --run
```

Expected: both commands pass.

- [ ] **Step 4: Commit**

Run:

```bash
git add research/BUILD_PLAN.md WORK_LOG.md handoff.md research/DATA_SOURCE_MAP.md core/wallet_quant.py utils/build_wallet_quant_report.py tests/test_wallet_quant.py desktop_api.py apps/desktop/src/App.tsx
git commit -m "Refocus on quant wallet tracking"
```
