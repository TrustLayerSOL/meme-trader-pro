from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.rejection_logger import DEFAULT_REJECT_PATH
from core.replay_visibility import build_replay_visibility_report


def load_jsonl(path: Path, limit: int = 500) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def main() -> int:
    rows = load_jsonl(ROOT / DEFAULT_REJECT_PATH)
    report = build_replay_visibility_report(rows)
    out = ROOT / "data" / "replay_visibility_report.json"
    out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)} records={report['counts']['records']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

