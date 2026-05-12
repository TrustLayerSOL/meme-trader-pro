# MemeTraderPro Agent Workflow

Permanent instructions for agents working in this repo.

Last updated: 2026-04-29

## Purpose

MemeTraderPro is a local Solana meme coin trading cockpit. The product direction is confirmation-mode trading, wallet intelligence, token risk inspection, manual protection/watchdog workflows, paper-first validation, and gated live execution.

Agents should make the system safer, clearer, more reliable, and more professional. Do not chase hype features at the expense of risk controls.

Current project priority:

- Treat measurable decision quality as the product backbone.
- Prefer canonical decision-ledger work over adding disconnected GUI panels.
- Route new automated social/catalyst inputs into the canonical decision ledger instead of creating a separate social dashboard truth.
- Separate pre-entry rejection, fast open-position monitoring, and slower deep watchdog inspection.
- Do not describe the slow watchdog as sub-second rug protection.

## Lead Agent Mandate

The main Codex agent is the lead agent for this project only.

Responsibilities:

- Move the project forward quickly while keeping work organized and safe.
- Keep this project completely separate from other projects.
- Review and integrate helper-agent work before considering it complete.
- Surface blockers or decisions clearly in `WORK_LOG.md` and to the overseer.
- Use branches/commits for meaningful completed work when appropriate.

Helper-agent rules:

- Use helper agents when parallel work would speed progress.
- Prefer 2-4 helper agents at once.
- Use more than 4 only when tasks are truly independent.
- Assign each helper one narrow task and one clear ownership area.
- No helper may edit files outside its assigned area.
- Do not assign two helpers to the same files at the same time.
- Helpers should update `WORK_LOG.md` with what they did, files changed, blockers, and next steps.
- The lead agent remains responsible for review, integration, verification, and final status.

Helper-agent hard limits:

- No live trading.
- No spending money.
- No deleting runtime data unless explicitly approved.
- No resetting git history.
- No exposing secrets.
- No irreversible changes.
- No bypassing safety gates.

## How To Work In This Repo

1. Read the relevant files before editing.
2. Keep changes scoped to the current task.
3. Prefer existing project patterns over new frameworks.
4. Preserve paper-first behavior.
5. Verify the changed area before reporting completion.
6. Update `WORK_LOG.md` after meaningful work.
7. Update `research/BUILD_PLAN.md` or notify the build-plan keeper when roadmap status changes.
8. Update `research/DATA_SOURCE_MAP.md` when data sources, tables, or dashboard panels change.
9. Leave runtime state understandable; do not hide errors by deleting files.

## What Not To Touch Without Explicit Reason

High-caution files and areas:

- `.env`
- private keys, wallet secrets, or RPC credentials
- `execution/*`
- live buy/sell wiring
- `data/memetrader.db`
- `data/*.json` runtime files
- launcher/process control code
- safety gates
- auto-sell controls

Do not make broad rewrites of these areas unless the user explicitly asks or the build plan clearly requires it.

## Safety Rules

- Paper mode is the default.
- Live trading must remain locked unless explicit safety gates pass.
- Never enable live buys or sells by default.
- Never bypass `core/execution_safety.py`.
- Manual protection auto-sell must stay disabled until prepared simulation exits, audit logs, kill switch behavior, and live safety gates are complete.
- Token-2022 is not automatically bad.
- Only hard reject mechanics known to be dangerous, such as permanent delegate, non-transferable tokens, default frozen accounts, or hostile transfer restrictions.
- Keep sell-route/quote feasibility as a required future live-execution gate.
- Do not promise or imply guaranteed trading profits in UI, docs, or marketing assets.

## Runtime State Rules

- Treat JSON files in `data/` as active local state.
- Keep JSON valid and human-readable.
- Do not delete state files to clear errors.
- If a file is malformed, repair it carefully and log what happened.
- Prefer adding `last_updated`, `reason`, `status`, and `source` fields to new state.
- When adding a new state source, add it to `research/DATA_SOURCE_MAP.md`.

## Commit Habits

Use branches/commits for meaningful completed work when appropriate.

Before committing:

- Check changed files first.
- Do not include unrelated user changes.
- Do not revert changes you did not make.
- Confirm safety-critical changes were verified.
- Use a concise commit message describing the outcome, not the process.
- Keep generated/cache files out of commits unless they are intentional project assets.
- Mention tests or verification in the final status.

Recommended commit message style:

- `Add watchdog simulation exits`
- `Surface data freshness in runtime health`
- `Document token risk source map`

## Progress Logging

Use `WORK_LOG.md` as the chronological work log.

For each meaningful work chunk, add:

- date,
- short title,
- changed files,
- what changed,
- verification performed,
- remaining risk or next step.

Use `research/BUILD_PLAN.md` for roadmap status, not detailed daily notes.

Use `research/OPEN_SOURCE_REPO_REVIEW.md` for external repo/library research.

Use `research/PROJECT_STATE.md` for larger handoff/state summaries.

## Current Roadmap Source

Primary roadmap:

- `research/BUILD_PLAN.md`

The highlighted current working section near the top of that file is authoritative. If the active focus changes, update that highlight.

## Agent Coordination

Main implementation agent:

- acts as lead agent for this repo,
- owns final integration and verification,
- assigns helper agents only narrow, non-overlapping work.

Build-plan keeper:

- maintains `research/BUILD_PLAN.md`,
- updates roadmap checkboxes,
- keeps current working section highlighted,
- records changelog entries.

Specialist agents:

- handle bounded research, marketing, review, or implementation subtasks,
- should return concise outputs,
- should not change safety-critical execution behavior unless specifically assigned.

## Verification Guide

Use the smallest check that proves the changed area still works.

| Change Type | Minimum Verification |
| --- | --- |
| Python module | `python3 -m py_compile <changed files>` |
| Dashboard | Compile dashboard and confirm `http://127.0.0.1:8501` responds |
| Watchdog | `trading_env/bin/python -m core.rug_watchdog_once` |
| Storage | `python3 utils/sync_state_to_sqlite.py` |
| Token inspector | Test safe Token-2022 pass and dangerous mechanics block |
| Settings | Save/load settings and confirm dashboard renders |
| Marketing asset | Save final asset under `marketing/` and log the prompt/source |

## Repo Docs

- `WORK_LOG.md` - chronological progress log.
- `research/BUILD_PLAN.md` - roadmap and current section.
- `research/DATA_SOURCE_MAP.md` - state files, tables, and panel mappings.
- `research/SAFE_EDITING_ZONES.md` - edit boundaries and cautions.
- `research/OPEN_SOURCE_REPO_REVIEW.md` - external repo research.
- `research/PROJECT_STATE.md` - larger project state/handoff notes.

## Product Bias

Favor work that improves:

- risk recognition,
- canonical candidate decision records,
- automated but auditable social/catalyst evidence,
- lane-separated paper evidence,
- explainable skipped candidates,
- paper-trade evidence,
- wallet reputation,
- watchdog protection,
- safe eventual execution,
- professional local GUI/UX.

Avoid work that mainly adds:

- blind launch sniping,
- artificial volume behavior,
- casino-style UI,
- social-only buy triggers,
- ungated live trading,
- opaque AI decisions.
