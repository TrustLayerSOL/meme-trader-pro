"""JSONL-backed feature snapshot store."""

from __future__ import annotations

import json
from pathlib import Path

from research.mtp_research.features.feature_models import FeatureSnapshot


class FeatureSnapshotStore:
    """Persist feature snapshots and upsert them by snapshot id."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/features/feature_snapshots.jsonl"))

    def load_all(self) -> list[FeatureSnapshot]:
        if not self.path.exists():
            return []

        snapshots: list[FeatureSnapshot] = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if text:
                    snapshots.append(FeatureSnapshot.from_dict(json.loads(text)))
        return snapshots

    def get_by_snapshot_id(self, snapshot_id: str) -> FeatureSnapshot | None:
        for snapshot in self.load_all():
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
        return None

    def upsert(self, snapshot: FeatureSnapshot) -> str:
        snapshots = self.load_all()
        for idx, existing in enumerate(snapshots):
            if existing.snapshot_id == snapshot.snapshot_id:
                snapshots[idx] = snapshot
                self._write_all(snapshots)
                return "updated"

        snapshots.append(snapshot)
        self._write_all(snapshots)
        return "inserted"

    def upsert_many(self, snapshots: list[FeatureSnapshot]) -> dict[str, int]:
        counts = {"inserted": 0, "updated": 0}
        for snapshot in snapshots:
            result = self.upsert(snapshot)
            counts[result] += 1
        return counts

    def _write_all(self, snapshots: list[FeatureSnapshot]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sorted_snapshots = sorted(
            snapshots,
            key=lambda snapshot: (
                snapshot.token_mint,
                snapshot.snapshot_ts,
                snapshot.window_seconds,
            ),
        )

        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for snapshot in sorted_snapshots:
                f.write(json.dumps(snapshot.to_dict(), sort_keys=True))
                f.write("\n")
        tmp_path.replace(self.path)
