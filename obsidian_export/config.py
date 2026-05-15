from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from core.env_loader import load_env


@dataclass(frozen=True)
class ObsidianExportConfig:
    vault_path: Path
    root_folder: str = "MemeTraderPro"
    data_dir: Path = Path("data")
    max_wallets: int | None = 250
    max_signals: int = 500
    max_rejected_signals: int = 250
    max_paper_trades: int = 500
    max_postmortems: int = 500

    @classmethod
    def from_env(cls) -> "ObsidianExportConfig":
        load_env()
        raw_path = os.getenv("OBSIDIAN_VAULT_PATH")
        if not raw_path:
            raise ValueError("Set OBSIDIAN_VAULT_PATH to the Obsidian vault folder before exporting.")

        return cls(
            vault_path=Path(raw_path).expanduser(),
            max_wallets=_env_int_or_none("OBSIDIAN_EXPORT_MAX_WALLETS", default=250),
            max_signals=_env_int("OBSIDIAN_EXPORT_MAX_SIGNALS", 500),
            max_rejected_signals=_env_int("OBSIDIAN_EXPORT_MAX_REJECTED_SIGNALS", 250),
            max_paper_trades=_env_int("OBSIDIAN_EXPORT_MAX_PAPER_TRADES", 500),
            max_postmortems=_env_int("OBSIDIAN_EXPORT_MAX_POSTMORTEMS", 500),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        return default


def _env_int_or_none(name: str, *, default: int | None = None) -> int | None:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    if raw in ("none", "None", "all", "ALL"):
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None
