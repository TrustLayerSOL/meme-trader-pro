# MemeTraderPro Desktop Shell

Tauri + React shell for the final double-click MemeTraderPro workstation.

Current status:

- Execution-locked for all live trading actions.
- Connects to the existing local desktop API at `http://127.0.0.1:8765`.
- Checks and starts the local read-only Python desktop API when launched from this repo.
- Does not call live trading, buy, sell, execution, or auto-sell routes.
- Allows scoped local metadata mutations for protected-position amount/decimals, wallet review decisions, and guarded wallet-list apply.
- Metadata POST routes use a launcher-issued session token when started through the desktop shell. These routes do not buy, sell, unlock live execution, or enable auto-sell.

Useful commands:

```bash
npm install
npm test
npm run check
npm run build:web
npm run build
```

Build outputs:

- `src-tauri/target/release/bundle/macos/MemeTraderPro.app`
- `src-tauri/target/release/bundle/dmg/MemeTraderPro_0.1.0_aarch64.dmg`

Next integration step:

- Expand the React cockpit until it replaces the static local web prototype.
