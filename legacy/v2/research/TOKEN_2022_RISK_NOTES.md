# Token-2022 Risk Notes

Last updated: 2026-04-29

## Why This Matters

Some Solana meme tokens can look healthy on price/market-cap charts while token mechanics or authority controls make them unsafe. A chart may continue climbing until liquidity is pulled or transfers become hostile, at which point market cap can collapse in less than a second.

For these cases, the best defense is pre-trade rejection plus very fast on-chain monitoring. A watchdog that only polls market price/liquidity every few seconds may confirm the damage after it happens, but it may not exit before the first collapse transaction settles.

## Token-2022 Extensions To Flag

Hard-reject extensions/mechanics:

- Permanent Delegate: can grant an authority power over token accounts for that mint. Solana docs state the permanent delegate can transfer or burn tokens in any token account for the mint.
- Non-transferable or custom transfer restrictions: hard reject for trading.
- Default frozen account state: hard reject for normal meme trading.

Needs-caution extensions/mechanics:

- Transfer Hook: executes custom program logic during token transfers. This can be legitimate, but for meme trading it adds transfer/sell-path uncertainty.
- Transfer Fee: charges fees on token movement. Legitimate in some assets, but must be understood before trading.
- Freeze authority present: caution unless normal/expected for the launch route.
- Mint authority present: caution unless normal/expected for the launch route.
- Unknown extension: caution until we classify it; do not hard reject solely because it is unknown.

## Bot Rules To Build

Pre-entry:

- Detect Token-2022 program owner for the mint.
- Decode mint extensions.
- Do not reject Token-2022 by itself. Most recent Pump.fun launches may use Token-2022.
- Hard reject only mechanics that make normal trading unsafe or give abnormal control, such as Permanent Delegate, Non-transferable, or default frozen accounts.
- Warn on Transfer Hook, Transfer Fee, unknown extensions, mint authority, or freeze authority.
- Dev reputation modifies scrutiny: 0 bonded projects = cautious, 2-4 = cautious but possible, 5+ bonded/migrated projects = usually passes this portion if extensions are benign.
- Verify sell quote before entry and re-check after entry.

Post-entry watchdog:

- Subscribe to token pool accounts and watched token accounts, not only price APIs.
- Monitor pool SOL/base liquidity balance changes.
- Monitor dev/creator/top-holder token sells.
- Monitor authority/extension-related changes where possible.
- Trigger emergency sell intent on liquidity drain, top-holder/dev sell, or sell-route degradation.

Expectation:

- If liquidity is drained in 1 transaction or 3 back-to-back transfers, a watchdog may not beat the collapse unless it sees the first harmful transaction before the sell route is destroyed.
- Therefore Token-2022/high-authority-risk tokens should usually be rejected before entry.

## Sources

- Solana Permanent Delegate docs: https://solana.com/developers/guides/token-extensions/permanent-delegate
- Solana Transfer Hook docs: https://solana.com/developers/guides/token-extensions/transfer-hook
- Solana token extensions overview: https://dev-solana.com/docs/token-extensions
- Chainstack Token-2022 transfer hooks / fee-on-transfer explainer: https://chainstack.com/solana-token-2022-fee-transfer-hooks/
