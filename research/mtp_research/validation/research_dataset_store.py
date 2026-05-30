"""JSONL-backed research dataset store."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


class ResearchDatasetStore:
    """Persist joined feature/outcome rows and upsert by row id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/backtests/research_dataset.jsonl"))

    def load_all(self) -> list[ResearchDatasetRow]:
        if not self.path.exists():
            return []
        rows: list[ResearchDatasetRow] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    rows.append(ResearchDatasetRow.from_dict(json.loads(text)))
        return rows

    def get_by_row_id(self, row_id: str) -> ResearchDatasetRow | None:
        for row in self.load_all():
            if row.row_id == row_id:
                return row
        return None

    def upsert(self, row: ResearchDatasetRow) -> str:
        rows = self.load_all()
        for idx, existing in enumerate(rows):
            if existing.row_id == row.row_id:
                rows[idx] = row
                self._write_all(rows)
                return "updated"
        rows.append(row)
        self._write_all(rows)
        return "inserted"

    def upsert_many(self, rows: list[ResearchDatasetRow]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        for row in rows:
            counts[self.upsert(row)] += 1
        return counts

    def _write_all(self, rows: list[ResearchDatasetRow]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_rows = sorted(
            rows,
            key=lambda row: (
                row.token_mint,
                row.snapshot_ts,
                row.window_seconds,
                row.horizon_seconds,
            ),
        )
        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for row in sorted_rows:
                f.write(json.dumps(row.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
