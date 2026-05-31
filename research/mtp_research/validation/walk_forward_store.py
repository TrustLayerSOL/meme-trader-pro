"""JSONL store for walk-forward validation results."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.walk_forward_models import WalkForwardValidationResult


class WalkForwardValidationStore:
    """Persist walk-forward validation results and upsert by validation id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/backtests/walk_forward_results.jsonl"))

    def load_all(self) -> list[WalkForwardValidationResult]:
        if not self.path.exists():
            return []
        results: list[WalkForwardValidationResult] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    results.append(WalkForwardValidationResult.from_dict(json.loads(text)))
        return results

    def get_by_validation_id(self, validation_id: str) -> WalkForwardValidationResult | None:
        for result in self.load_all():
            if result.validation_id == validation_id:
                return result
        return None

    def upsert(self, result: WalkForwardValidationResult) -> str:
        results = self.load_all()
        for index, existing in enumerate(results):
            if existing.validation_id == result.validation_id:
                results[index] = result
                self._write_all(results)
                return "updated"
        results.append(result)
        self._write_all(results)
        return "inserted"

    def upsert_many(self, results: list[WalkForwardValidationResult]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        for result in results:
            counts[self.upsert(result)] += 1
        return counts

    def _write_all(self, results: list[WalkForwardValidationResult]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_results = sorted(results, key=lambda result: (result.created_at, result.validation_id))
        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for result in sorted_results:
                f.write(json.dumps(result.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
