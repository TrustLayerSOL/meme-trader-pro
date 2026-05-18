# Discord Intelligence Setup

MemeTraderPro's Discord layer is a sparse research-review output, not a trading alert firehose.

It should only surface:

- wallet review transitions,
- behavioral pattern candidates,
- replay-validation blockers,
- regime-monitor gaps,
- evidence recovery milestones,
- wallet degradation review items.

It must not imply live execution is safe, send every raw wallet event, promote wallets automatically, or trigger trading.

## Recommended Channels

Create these channels in a MemeTraderPro-specific Discord server or category:

- `#wallet-review`
- `#behavioral-patterns`
- `#replay-validation`
- `#regime-monitor`
- `#wallet-degradation`
- `#research-updates`

## Local Webhook Config

Webhook URLs are secrets. Keep them out of git.

Preferred local file:

```json
{
  "webhooks": {
    "#wallet-review": "https://discord.com/api/webhooks/...",
    "#behavioral-patterns": "https://discord.com/api/webhooks/...",
    "#replay-validation": "https://discord.com/api/webhooks/...",
    "#regime-monitor": "https://discord.com/api/webhooks/...",
    "#wallet-degradation": "https://discord.com/api/webhooks/...",
    "#research-updates": "https://discord.com/api/webhooks/..."
  }
}
```

Save that file locally as:

```text
data/discord_webhooks.local.json
```

This path is ignored by git through the existing `data/*.json` rule.

Environment variable alternatives:

- `MTP_DISCORD_WEBHOOK_URL` for one fallback webhook.
- `MTP_DISCORD_WEBHOOK_WALLET_REVIEW`
- `MTP_DISCORD_WEBHOOK_BEHAVIORAL_PATTERNS`
- `MTP_DISCORD_WEBHOOK_REPLAY_VALIDATION`
- `MTP_DISCORD_WEBHOOK_REGIME_MONITOR`
- `MTP_DISCORD_WEBHOOK_WALLET_DEGRADATION`
- `MTP_DISCORD_WEBHOOK_RESEARCH_UPDATES`

## Commands

Generate the research-only event report:

```bash
./trading_env/bin/python utils/build_discord_intelligence_layer.py
```

Preview the dispatch plan without sending:

```bash
./trading_env/bin/python utils/dispatch_discord_intelligence.py
```

Send only after webhooks are configured and the report has been reviewed:

```bash
./trading_env/bin/python utils/dispatch_discord_intelligence.py --send
```

Successful sends are recorded locally in:

```text
data/discord_dispatch_ledger.local.json
```

That ledger is ignored by git through the existing `data/*.json` rule and prevents repeat dispatcher runs from reposting the same event IDs.

## Safety Rules

- Default mode is dry-run.
- `--send` is required before any Discord post.
- Already-sent event IDs are skipped by the local dispatch ledger.
- Missing channel webhooks block only those channel events.
- Dispatch never changes wallet trust, wallet lists, paper trades, or live execution.
- Live execution remains locked.

## Troubleshooting

- If a webhook post returns `403`, verify the copied Discord webhook URL with a single controlled test post before changing routing logic.
- MemeTraderPro sends Discord posts with an explicit `User-Agent` header because Discord can reject default Python request clients.
- Do not paste webhook URLs into logs, committed docs, or chat transcripts.
