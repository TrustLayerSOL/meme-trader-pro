"""JSONL-backed outcome label store."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.validation.outcome_models import OutcomeLabel


class OutcomeLabelStore:
    """Persist validation outcome labels and upsert by outcome id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/backtests/outcome_labels.jsonl"))

    def load_all(self) -> list[OutcomeLabel]:
        if not self.path.exists():
            return []

        labels: list[OutcomeLabel] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    labels.append(OutcomeLabel.from_dict(json.loads(text)))
        return labels

    def get_by_outcome_id(self, outcome_id: str) -> OutcomeLabel | None:
        for label in self.load_all():
            if label.outcome_id == outcome_id:
                return label
        return None

    def upsert(self, label: OutcomeLabel) -> str:
        labels = self.load_all()
        for idx, existing in enumerate(labels):
            if existing.outcome_id == label.outcome_id:
                labels[idx] = label
                self._write_all(labels)
                return "updated"

        labels.append(label)
        self._write_all(labels)
        return "inserted"

    def upsert_many(self, labels: list[OutcomeLabel]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        if not labels:
            return counts

        existing_labels = {label.outcome_id: label for label in self.load_all()}
        for label in labels:
            if label.outcome_id in existing_labels:
                counts["updated"] += 1
            else:
                counts["inserted"] += 1
            existing_labels[label.outcome_id] = label
        self._write_all(list(existing_labels.values()))
        return counts

    def replace_all(self, labels: list[OutcomeLabel]) -> dict[str, int]:
        self._write_all(labels)
        return {"inserted": len(labels), "updated": 0}

    def _write_all(self, labels: list[OutcomeLabel]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_labels = sorted(
            labels,
            key=lambda label: (
                label.token_mint,
                label.snapshot_ts,
                label.horizon_seconds,
            ),
        )

        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for label in sorted_labels:
                f.write(json.dumps(label.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
