from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator


class T007EvidenceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._evidence_keys: set[tuple[str, str]] = set()
        self._snapshot_keys: set[tuple[str, str, str]] = set()
        self._transition_keys: set[tuple[str, str, str, str]] = set()
        self._load_existing_keys()

    def _load_existing_keys(self) -> None:
        for row in self.read_jsonl("evidence_records.jsonl"):
            self._evidence_keys.add((str(row.get("signature") or ""), str(row.get("source_lane") or "")))
        for row in self.read_jsonl("account_snapshot_log.jsonl"):
            self._snapshot_keys.add((str(row.get("pubkey") or ""), str(row.get("slot") or ""), str(row.get("commitment") or "")))
        for row in self.read_jsonl("lifecycle_transitions.jsonl"):
            self._transition_keys.add(
                (
                    str(row.get("mint") or ""),
                    str(row.get("next_state") or ""),
                    str(row.get("signature") or ""),
                    str(row.get("reason") or ""),
                )
            )

    def read_jsonl(self, name: str) -> Iterator[dict[str, Any]]:
        path = self.root / name
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def _append(self, name: str, row: dict[str, Any]) -> None:
        with (self.root / name).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    def write_evidence(self, row: dict[str, Any]) -> str:
        key = (str(row.get("signature") or ""), str(row.get("source_lane") or ""))
        if key in self._evidence_keys:
            return "duplicate"
        self._evidence_keys.add(key)
        self._append("evidence_records.jsonl", dict(row))
        return "written"

    def write_account_snapshot(self, row: dict[str, Any]) -> str:
        key = (str(row.get("pubkey") or ""), str(row.get("slot") or ""), str(row.get("commitment") or ""))
        if key in self._snapshot_keys:
            return "duplicate"
        self._snapshot_keys.add(key)
        self._append("account_snapshot_log.jsonl", dict(row))
        return "written"

    def write_lifecycle_transition(self, row: dict[str, Any]) -> str:
        key = (
            str(row.get("mint") or ""),
            str(row.get("next_state") or ""),
            str(row.get("signature") or ""),
            str(row.get("reason") or ""),
        )
        if key in self._transition_keys:
            return "duplicate"
        self._transition_keys.add(key)
        self._append("lifecycle_transitions.jsonl", dict(row))
        return "written"
