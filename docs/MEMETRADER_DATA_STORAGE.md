# MemeTraderPro Data Storage

MemeTraderPro generated research data now lives on the portable ORICO drive.

```text
/Volumes/ORICO/MemeTraderPro
```

Set this environment variable before running data-heavy research commands:

```bash
export MEMETRADER_DATA_ROOT="/Volumes/ORICO/MemeTraderPro"
```

The repo-local `data/` tree is intentionally kept as lightweight placeholders only. Do not store large generated JSONL, report, raw transaction, lifecycle, or backtest artifacts in the repo checkout.

## Migration Verification

The migration was verified before source duplicates were removed:

```text
/Volumes/ORICO/MemeTraderPro/migration_verification_report.md
/Volumes/ORICO/MemeTraderPro/migration_manifest.json
```

The old external-drive copy under `/Volumes/Polymarket Data/MemeTraderPro/data` was removed after verification. A migration pointer remains at:

```text
/Volumes/Polymarket Data/MemeTraderPro/README_MIGRATED_TO_ORICO.txt
```

Differing internal lifecycle files were preserved under:

```text
/Volumes/ORICO/MemeTraderPro/archives/internal_repo_conflicts/data
```
