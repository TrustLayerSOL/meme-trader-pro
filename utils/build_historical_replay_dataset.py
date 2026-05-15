from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research.historical_replay_dataset import build_historical_replay_dataset
from utils.build_wallet_outcome_ledger import build_records


DEFAULT_OUT_DIR = ROOT / "data" / "historical_replay"


def write_replay_dataset_files(
    records: list[dict[str, Any]],
    *,
    out_dir: Path | str = DEFAULT_OUT_DIR,
    generated_at: float | None = None,
) -> dict[str, Any]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    dataset = build_historical_replay_dataset(records, generated_at=generated_at)
    events_path = out_path / "replay_events.jsonl"
    summary_path = out_path / "summary.json"

    with events_path.open("w", encoding="utf-8") as fh:
        for event in dataset["events"]:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    summary = {
        key: value
        for key, value in dataset.items()
        if key != "events"
    }
    summary["events_path"] = str(events_path)
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "events_path": str(events_path),
        "summary_path": str(summary_path),
        "counts": dataset["counts"],
    }


def main() -> int:
    result = write_replay_dataset_files(build_records())
    print(
        "wrote {} events={} unsafe={}".format(
            Path(result["events_path"]).relative_to(ROOT),
            result["counts"].get("events", 0),
            result["counts"].get("unsafe_events", 0),
        )
    )
    print("wrote {}".format(Path(result["summary_path"]).relative_to(ROOT)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
