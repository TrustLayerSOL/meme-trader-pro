#!/usr/bin/env zsh
set -euo pipefail

cd /Users/dianeposs/Projects/meme-trader-pro

export MEMETRADER_DATA_ROOT=/Volumes/ORICO/MemeTraderPro

exec ./trading_env/bin/python -u -m research.mtp_research.validation.run_forward_efficient_mover_observer \
  --mode observe-lifecycle \
  --sample official_lifecycle_watch_v2 \
  --source helius-pumpfun-no-laserstream \
  --data-root /Volumes/ORICO/MemeTraderPro \
  --target-births 1000 \
  --target-crossed-20k 300 \
  --max-runtime-minutes 360 \
  --max-helius-credits 500000 \
  --max-active-birth-followups 300 \
  --signatures-per-mint 2 \
  --transactions-per-mint 2 \
  --execute
