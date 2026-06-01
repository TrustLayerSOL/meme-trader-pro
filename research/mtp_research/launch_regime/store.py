"""JSONL stores for launch-regime artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")


class JsonlArtifactStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load_all(self, from_dict: Callable[[dict], T]) -> list[T]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    rows.append(from_dict(json.loads(text)))
        return rows

    def write_all(self, rows: list[object], sort_key: Callable[[object], object] | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(rows, key=sort_key) if sort_key else rows
        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for row in ordered:
                f.write(json.dumps(row.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
