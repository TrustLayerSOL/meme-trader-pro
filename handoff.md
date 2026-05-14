# MemeTraderPro Handoff

Last updated: 2026-05-14

## Current Repo

Use this repo as the real working copy:

`/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`

`/Users/dianeposs/Desktop/Jordan/meme_trader_pro` is intended to remain only a compatibility symlink to the real repo.

## Most Recent User Direction

- Check file/repo integrity after external upgrade work.
- Determine why the GitHub upload looked messy.
- Verify GitHub state and repair local issues where appropriate.

## Current Status

- Live execution remains locked.
- Desktop API is running on `127.0.0.1:8765`.
- Paper bot/scanner, watchdog, and wallet discovery are running in `screen` sessions from `/Users/dianeposs/Desktop/Jordan 2/meme_trader_pro`.
- Runtime health reports bot, websocket, scanner, market, quotes, watchdog, open-position monitor, wallet discovery, and Market Radar fresh.
- Runtime currently reports 518 tracked wallets, 5719 paper-watch wallets, and 6237 observed wallets.
- Active Git branch is `phase6-protection-exits`, synced with `origin/phase6-protection-exits`.
- GitHub default branch is `main`; `origin/main` has one newer README-only commit that local `main` does not have.

## Performance Snapshot Excluding PENGUINZ

- Total trades: 38
- Closed: 29
- Open: 2
- Failed: 7
- Closed PnL: `-$280.93`
- Open unrealized PnL: about `-$1.98`
- Closed win rate: `3.4%`
- Excluded outlier: `Nietzschean Penguin` / PENGUINZ, about `+$797.21`

Interpretation: without PENGUINZ, the current paper data does not prove edge. The immediate priority is cleaner sample collection, not declaring profitability.

## Latest Change

Completed file-integrity and GitHub audit after external upgrade work.

Findings:

- GitHub repo `TrustLayerSOL/meme-trader-pro` is reachable, public, and the current user has admin permission.
- No open PRs were present.
- The upload confusion is likely branch/state confusion, not a broken GitHub repo: active work is on `phase6-protection-exits`; default branch is `main`.
- `data/memetrader.db` was genuinely malformed. The corrupt copy and sidecars were archived in `data/archives/db_repair_20260514_020339/`.
- The recovered DB was verified and installed as the active `data/memetrader.db`.
- React desktop had type/test drift from upgrade work; shared API types were updated and Decision Ledger rich evidence rows were restored.
- `data/rejected_signals/` is runtime-generated and is now ignored.

Files changed in the audit:

- `.gitignore`
- `apps/desktop/src/components/DecisionLedger.tsx`
- `apps/desktop/src/lib/api.ts`
- `apps/desktop/src/lib/decisions.ts`
- `WORK_LOG.md`
- `handoff.md`

Verification:

- Python core/desktop/market tests passed 250 tests.
- Python compile check passed.
- JSON parse check passed.
- SQLite integrity and quick checks returned `ok`.
- Desktop TypeScript check passed.
- Desktop React tests passed 41 tests.
- Tauri/macOS desktop build completed and produced `.app` and `.dmg`.
- Desktop API `/api/runtime` is online and live execution remains locked.

## Prior Change

Added broad paper-watch wallet expansion.

Files changed:

- `core/wallet_discovery.py`
- `core/wallet_discovery_scheduler.py`
- `utils/discover_candidate_wallets.py`
- `utils/run_wallet_discovery_scheduler.py`
- `core/settings_manager.py`
- `tests/test_core_logic.py`
- `WORK_LOG.md`
- `handoff.md`
- `data/candidate_wallets.json`
- `data/paper_watch_wallets.json`

Behavior:

- Discovery now mines three wallet sources: local skipped runners, current Dexscreener Solana trending/boosted mints, and paper winners.
- Candidate report expanded to 309 wallets: 240 untracked, 69 already tracked.
- Paper-watch expanded from 1 wallet to 381 total wallets after merging new runner wallets with existing paper-watch state.
- Paper-watch wallets are observation only and are not live trade drivers.
- Demotion exists as a lifecycle review action: poor paper performance flags wallets for `DEMOTE_OFF_WATCH_REVIEW`; no automatic deletion yet.

Verification:

- Candidate wallet/wallet lifecycle/scheduler tests passed 18 tests.
- Compile checks passed for changed wallet discovery modules.
- Runtime confirms bot/scanner/websocket online and subscribed to 899 observed wallets.

## Next Logical Work

1. Decide branch integration path: merge/open PR from `phase6-protection-exits` into `main`, or keep `phase6-protection-exits` as the working branch intentionally.
2. Watch runtime pressure after expanding observed wallets; scanner active tasks/backpressure should not stay overloaded.
3. Add a clear GUI panel or report section showing paper-watch wallet performance, promotion candidates, and demotion candidates.
4. Let paper-watch collect closed outcomes before promoting any wallet to trusted.
5. Keep sample reporting lane-separated: wallet-main, Market Radar, exploration, manual/protected, and paper-watch source.
