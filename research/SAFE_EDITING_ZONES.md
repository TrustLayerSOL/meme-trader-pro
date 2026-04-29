# MemeTraderPro Safe Editing Zones

Last updated: 2026-04-29

This repo is being upgraded while runtime state and local dashboard workflows are active. Use this guide to avoid accidental regressions.

## Good First Places To Edit

| Area | Files | Notes |
| --- | --- | --- |
| Dashboard UI | `dashboard/dashboard.py` | Keep panels operational and data-dense. Prefer small helper functions over large rewrites. |
| Risk rules | `core/anti_rug.py`, `core/token_inspector.py`, `core/dev_analyzer.py` | Add tests or sample checks for hard rejects and warnings. |
| Confirmation logic | `core/confirmation_filter.py`, `core/scoring_engine.py`, `core/scanner.py` | Preserve paper-first behavior. Store reasons for passes and rejects. |
| Watchdog | `core/rug_watchdog.py`, `core/rug_watchdog_once.py` | Keep alert-only behavior unless live execution gates explicitly allow otherwise. |
| Data/persistence | `core/storage.py`, `utils/sync_state_to_sqlite.py` | Preserve existing JSON compatibility until the dashboard is migrated. |
| Settings | `core/settings_manager.py`, `data/bot_settings.json` | Validate new settings and keep defaults conservative. |
| Research/docs | `research/*.md` | Keep status, decisions, and build plan current. |

## High-Caution Areas

| Area | Why |
| --- | --- |
| `execution/*` | This can eventually touch real funds. Live execution must remain gated and audit-logged. |
| `.env` | Contains local secrets/config. Do not print or copy values into docs. |
| `data/*.json` | Runtime state. Edit carefully; malformed JSON can break panels. |
| `data/memetrader.db` | Durable local memory. Use migrations/utilities rather than manual binary edits. |
| launcher/process control | Bad process handling can leave duplicate bots/watchdogs running. |

## Do Not Do Without Explicit Intent

- Do not enable live buying or selling by default.
- Do not remove execution gates, safety checks, or paper-mode defaults.
- Do not treat Token-2022 itself as a hard reject.
- Do not hard reject metadata-only Token-2022 mints.
- Do not auto-sell protected positions until the live execution safety checklist is complete.
- Do not delete runtime data files just to clear errors.
- Do not move `.md` files back to the repo root; keep docs under `research/`.

## Required Verification For Common Changes

| Change Type | Minimum Verification |
| --- | --- |
| Python module edit | `python3 -m py_compile <changed files>` |
| Dashboard edit | Compile dashboard and check `http://127.0.0.1:8501` responds. |
| Watchdog edit | Run `trading_env/bin/python -m core.rug_watchdog_once` when network/RPC is available. |
| Storage edit | Run `python3 utils/sync_state_to_sqlite.py` and inspect Data Store counts. |
| Token inspector edit | Test metadata-only Token-2022 passes and dangerous extensions block/warn as expected. |
| Settings edit | Save/load settings and confirm dashboard renders Strategy Settings. |

## Agent Workflow

When a builder finishes meaningful work:

1. Update the relevant code/docs.
2. Run the minimum verification.
3. Update `research/BUILD_PLAN.md`.
4. Add or update `research/DATA_SOURCE_MAP.md` if data sources changed.
5. Tell the plan keeper agent what changed so the roadmap stays honest.

## Current Product Bias

MemeTraderPro should become a safer confirmation-trading cockpit, not a blind launch sniper. Prefer changes that improve:

- faster risk recognition,
- better skipped-candidate explanations,
- better paper-trade evidence,
- stronger wallet reputation signals,
- clearer watchdog protection,
- safer eventual execution gates.
