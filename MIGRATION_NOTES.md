# Migration Notes

## Summary

Legacy v2 code was preserved and a v3 scaffold was added at repository root while keeping operational safety constraints in mind.

## What was moved to `legacy/v2/`

- v2 source code, scripts, dashboards, tests, docs, configuration, and supporting artifacts
- where files were tracked, move was done with `git mv` to preserve history

## v1 status

No standalone v1 folder was found at migration time.
`legacy/v1/README.md` documents this and keeps the location available.

## Exclusions and manual follow-up

Excluded by design:

- `.env`
- `trading_env/`, `venv/`, `.venv/`
- `node_modules/`, `dist/`, `build/`
- cache directories (`__pycache__/`, `.pytest_cache/`)
- large runtime artifacts that were intentionally not moved into the v3-facing root scaffold
- OS artifacts (`.DS_Store`)

Manual follow-up:

- confirm whether large historical runtime artifacts should be snapshotted under `legacy/v2`
- verify that all required v3 build/test scripts are added before implementing active logic

## Root cleanup (v3 clean root pass)

- Moved `live_state.json` and `live_state 2.json` from repository root into
  `legacy/v2/runtime_snapshots/` for safe archival.
- Moved root `logs/` into `legacy/v2/logs/` to keep historical runtime output
  out of the v3 root while preserving it.
- Removed root cache/runtime artifacts: `__pycache/`, `.pytest_cache/`, and `.DS_Store`.
- Kept `.env` and `trading_env/` at repository root by design and added/kept ignore
  rules for both so they remain intentionally out of versioned v3 tracking:
  - `.env`
  - `.env.*`
  - `trading_env/`
