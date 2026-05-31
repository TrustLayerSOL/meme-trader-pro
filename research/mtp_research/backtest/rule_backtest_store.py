"""JSONL store for rule backtest results."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.backtest.rule_backtest_models import RuleBacktestResult


class RuleBacktestStore:
    """Persist rule backtest results and upsert by result id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/backtests/rule_backtest_results.jsonl"))

    def load_all(self) -> list[RuleBacktestResult]:
        if not self.path.exists():
            return []
        results: list[RuleBacktestResult] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    results.append(RuleBacktestResult.from_dict(json.loads(text)))
        return results

    def get_by_result_id(self, result_id: str) -> RuleBacktestResult | None:
        for result in self.load_all():
            if result.result_id == result_id:
                return result
        return None

    def upsert(self, result: RuleBacktestResult) -> str:
        results = self.load_all()
        for index, existing in enumerate(results):
            if existing.result_id == result.result_id:
                results[index] = result
                self._write_all(results)
                return "updated"
        results.append(result)
        self._write_all(results)
        return "inserted"

    def upsert_many(self, results: list[RuleBacktestResult]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        for result in results:
            counts[self.upsert(result)] += 1
        return counts

    def _write_all(self, results: list[RuleBacktestResult]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_results = sorted(results, key=lambda result: (result.created_at, result.result_id))
        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for result in sorted_results:
                f.write(json.dumps(result.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
