"""JSONL store for thesis decisions."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.thesis_models import ThesisDecision


class ThesisDecisionStore:
    """Persist thesis decisions and upsert by decision id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/backtests/thesis_decisions.jsonl"))

    def load_all(self) -> list[ThesisDecision]:
        if not self.path.exists():
            return []
        decisions: list[ThesisDecision] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    decisions.append(ThesisDecision.from_dict(json.loads(text)))
        return decisions

    def get_by_decision_id(self, decision_id: str) -> ThesisDecision | None:
        for decision in self.load_all():
            if decision.decision_id == decision_id:
                return decision
        return None

    def upsert(self, decision: ThesisDecision) -> str:
        decisions = self.load_all()
        for index, existing in enumerate(decisions):
            if existing.decision_id == decision.decision_id:
                decisions[index] = decision
                self._write_all(decisions)
                return "updated"
        decisions.append(decision)
        self._write_all(decisions)
        return "inserted"

    def upsert_many(self, decisions: list[ThesisDecision]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        for decision in decisions:
            counts[self.upsert(decision)] += 1
        return counts

    def _write_all(self, decisions: list[ThesisDecision]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_decisions = sorted(decisions, key=lambda item: (item.thesis_id, item.created_at))
        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for decision in sorted_decisions:
                f.write(json.dumps(decision.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
