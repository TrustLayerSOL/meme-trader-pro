"""Shared filesystem paths for MemeTraderPro research artifacts."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_LAKE_ROOT = Path("/Volumes/ORICO/MemeTraderPro")
DATA_ROOT_ENV_VAR = "MEMETRADER_DATA_ROOT"


def data_lake_root() -> Path:
    return Path(os.environ.get(DATA_ROOT_ENV_VAR, str(DEFAULT_DATA_LAKE_ROOT))).expanduser()


def data_lake_path(*parts: str) -> Path:
    return data_lake_root().joinpath(*parts)
