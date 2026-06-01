"""JSONL-backed raw transaction replay cache."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


@dataclass
class RawTransactionRecord:
    """A raw Helius/Solana transaction body stored for replayable research."""

    signature: str
    slot: int | None
    block_time: int | None
    success: bool | None
    address: str | None = None
    role: str = "unknown"
    token_mint: str | None = None
    source: str = "helius_rpc"
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_json: dict[str, Any] = field(default_factory=dict)
    metadata_json: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "slot": self.slot,
            "block_time": self.block_time,
            "success": self.success,
            "address": self.address,
            "role": self.role,
            "token_mint": self.token_mint,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
            "raw_json": self.raw_json,
            "metadata_json": self.metadata_json,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RawTransactionRecord":
        return cls(
            signature=payload["signature"],
            slot=payload.get("slot"),
            block_time=payload.get("block_time"),
            success=payload.get("success"),
            address=payload.get("address"),
            role=payload.get("role", "unknown"),
            token_mint=payload.get("token_mint"),
            source=payload.get("source", "helius_rpc"),
            fetched_at=datetime.fromisoformat(payload["fetched_at"]),
            raw_json=dict(payload.get("raw_json", {})),
            metadata_json=dict(payload.get("metadata_json", {})),
        )


class RawTransactionStore:
    """Persist raw transactions and upsert them by signature."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/raw/helius_transactions.jsonl"))

    def load_all(self) -> list[RawTransactionRecord]:
        return list(self.iter_all())

    def iter_all(self) -> Iterator[RawTransactionRecord]:
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    yield RawTransactionRecord.from_dict(json.loads(text))

    def get_by_signature(self, signature: str) -> RawTransactionRecord | None:
        for record in self.load_all():
            if record.signature == signature:
                return record
        return None

    def upsert(self, record: RawTransactionRecord) -> str:
        records = self.load_all()
        for idx, existing in enumerate(records):
            if existing.signature == record.signature:
                records[idx] = record
                self._write_all(records)
                return "updated"

        records.append(record)
        self._write_all(records)
        return "inserted"

    def upsert_many(self, records: list[RawTransactionRecord]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        if not records:
            return counts

        existing_records = {record.signature: record for record in self.load_all()}
        for record in records:
            if record.signature in existing_records:
                counts["updated"] += 1
            else:
                counts["inserted"] += 1
            existing_records[record.signature] = record
        self._write_all(list(existing_records.values()))
        return counts

    def append_new_many(self, records: list[RawTransactionRecord]) -> dict[str, int]:
        """Append records already known to be new by signature.

        Historical backfill filters existing signatures before hydration. In that
        path, rewriting the complete raw replay cache for every target is wasted
        work and dominates runtime once the file gets large.
        """
        counts = {"inserted": 0, "updated": 0}
        if not records:
            return counts

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record.to_dict(), sort_keys=True))
                f.write("\n")
                counts["inserted"] += 1
        return counts

    def _write_all(self, records: list[RawTransactionRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_records = sorted(
            records,
            key=lambda record: (
                record.block_time is None,
                record.block_time or 0,
                record.slot is None,
                record.slot or 0,
                record.signature,
            ),
        )

        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for record in sorted_records:
                f.write(json.dumps(record.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
