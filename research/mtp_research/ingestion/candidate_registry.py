"""JSONL-backed launch candidate registry for v3 discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from research.mtp_research.ingestion.models import LaunchCandidate


class CandidateRegistry:
    """Persist and upsert launch candidates into a JSONL registry."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path or Path("data/normalized/candidate_registry.jsonl"))

    def load_all(self) -> list[LaunchCandidate]:
        if not self.path.exists():
            return []

        candidates = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                candidates.append(LaunchCandidate.from_dict(json.loads(text)))

        return candidates

    def get_by_mint(self, token_mint: str) -> LaunchCandidate | None:
        for candidate in self.load_all():
            if candidate.token_mint == token_mint:
                return candidate
        return None

    def upsert(self, candidate: LaunchCandidate) -> str:
        existing = self.load_all()
        updated = False

        for idx, current in enumerate(existing):
            if current.token_mint == candidate.token_mint:
                existing[idx] = current.merge_with(candidate)
                updated = True
                break

        if not updated:
            existing.append(candidate)

        self._write_all(existing)
        return "updated" if updated else "inserted"

    def _write_all(self, candidates: Iterable[LaunchCandidate]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        candidates_list = list(candidates)
        candidates_list.sort(key=lambda c: c.first_seen_ts)

        tmp_path = self.path.with_suffix(".jsonl.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            for candidate in candidates_list:
                f.write(json.dumps(candidate.to_dict()))
                f.write("\n")

        tmp_path.replace(self.path)
