# Desktop GUI Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first non-Streamlit desktop-style cockpit that reads existing MemeTraderPro state through a local read-only API and displays a professional Axiom-like trading workstation.

**Architecture:** Add a stdlib Python server that serves static files from `desktop_gui/` and read-only JSON endpoints backed by existing JSON files and SQLite token snapshots. The UI is static HTML/CSS/JS for now so it requires no package installation; it can later be moved behind Tauri/Electron or rewritten in React without changing the data contract.

**Tech Stack:** Python stdlib `http.server`, SQLite, existing core helpers, static HTML/CSS/JavaScript, no live execution wiring.

---

### Task 1: Read-Only Desktop API Server

**Files:**
- Create: `desktop_api.py`
- Test: `tests/test_desktop_api.py`

- [x] **Step 1: Write tests for state aggregation and route safety**

Create tests that import pure helper functions from `desktop_api.py`, verify overview keys, verify action endpoints are not exposed, and verify candle rows are JSON-safe.

- [x] **Step 2: Implement pure helpers**

Implement `build_overview_payload`, `build_positions_payload`, `build_candles_payload`, and `route_request`. Helpers must read state defensively and never mutate runtime files.

- [x] **Step 3: Implement HTTP server**

Serve `/`, static assets under `/assets/`, and read-only `/api/overview`, `/api/positions`, `/api/candles?mint=...`. Return 404 for unknown routes and 405 for mutation verbs.

- [x] **Step 4: Verify**

Run `python3 -m py_compile desktop_api.py tests/test_desktop_api.py` and `python3 -m unittest tests.test_desktop_api`.

### Task 2: Static Pro Cockpit UI

**Files:**
- Create: `desktop_gui/index.html`
- Create: `desktop_gui/assets/styles.css`
- Create: `desktop_gui/assets/app.js`

- [x] **Step 1: Build shell layout**

Create a dense dark trading workstation with top navigation, status rail, main chart area, position list, right-side protection/action panel, and bottom tab strip.

- [x] **Step 2: Wire API reads**

Use `fetch` to read `/api/overview`, `/api/positions`, and `/api/candles?mint=...`; render loading, empty, stale, and error states.

- [x] **Step 3: Keep actions safe**

Render buttons for Exit Early and Add Position as disabled/locked labels until a future simulated intent API is explicitly implemented. Do not call execution modules.

- [x] **Step 4: Verify static files exist and API serves them**

Start `desktop_api.py` on a non-conflicting local port and confirm `/`, `/api/overview`, `/api/positions`, and `/api/candles` return expected HTTP statuses.

### Task 3: Launcher And Docs

**Files:**
- Create: `Start MemeTraderPro Desktop.command`
- Modify: `WORK_LOG.md`
- Modify: `research/BUILD_PLAN.md`
- Modify: `research/DATA_SOURCE_MAP.md`

- [x] **Step 1: Add double-click launcher**

Create a macOS command file that starts the local desktop API on `127.0.0.1:8765` and opens the browser to it.

- [x] **Step 2: Update docs**

Record the new desktop GUI surface, read-only API contract, and current limitations.

- [x] **Step 3: Verify launcher syntax and runtime**

Make the launcher executable, run the server, curl key routes, and stop the test server.
