from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SIGNAL_CONTEXT_PATH = Path("data/signal_contexts/contexts.jsonl")


def record_signal_context(
    signal_context: dict[str, Any],
    *,
    path: Path | None = None,
) -> Path:
    path = Path(path or DEFAULT_SIGNAL_CONTEXT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(signal_context) if isinstance(signal_context, dict) else {"raw": signal_context}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    return path

