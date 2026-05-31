"""Dataset sufficiency diagnostics for rule and walk-forward readiness."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from research.mtp_research.validation.research_dataset_models import ResearchDatasetRow


def summarize_dataset_sufficiency(
    rows: list[ResearchDatasetRow],
    token_mints: set[str] | None = None,
) -> dict[str, Any]:
    real_rows = [row for row in rows if token_mints is None or row.token_mint in token_mints]
    return {
        "total_rows": len(rows),
        "real_only_rows": len(real_rows),
        "rows_with_entry_price": sum(1 for row in rows if row.entry_price is not None),
        "rows_with_forward_return": sum(1 for row in rows if row.forward_return is not None),
        "rows_by_label_quality": dict(sorted(Counter(row.label_quality for row in rows).items())),
        "rows_by_window_horizon": dict(sorted(Counter(f"{row.window_name}/{row.horizon_name}" for row in rows).items())),
        "rows_by_entry_price_source": dict(sorted(Counter(row.entry_price_source or "missing" for row in rows).items())),
    }


def summarize_rule_selectability(rows: list[ResearchDatasetRow]) -> dict[str, Any]:
    return {
        "rows_with_entry_and_forward_return": sum(
            1 for row in rows if row.entry_price is not None and row.forward_return is not None
        ),
        "rows_min_label_quality_sparse": sum(1 for row in rows if row.label_quality in {"sparse", "good"}),
        "rows_min_label_quality_good": sum(1 for row in rows if row.label_quality == "good"),
        "rows_possible_buy_positive": sum(1 for row in rows if row.possible_buy_count > 0),
        "rows_possible_sell_positive": sum(1 for row in rows if row.possible_sell_count > 0),
        "rows_with_net_base_flow": sum(1 for row in rows if row.net_base_flow != 0),
    }


def build_dataset_sufficiency_report(
    rows: list[ResearchDatasetRow],
    token_mints: set[str] | None = None,
) -> dict[str, Any]:
    return {
        "report_id": f"dataset_sufficiency_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sufficiency": summarize_dataset_sufficiency(rows, token_mints=token_mints),
        "selectability": summarize_rule_selectability(rows if token_mints is None else [row for row in rows if row.token_mint in token_mints]),
        "warning": "This is a diagnostic report, not a trading signal.",
    }


def write_dataset_sufficiency_json(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_dataset_sufficiency_markdown(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dataset Sufficiency Report",
        "",
        f"- created_at: `{report['created_at']}`",
        f"- report_id: `{report['report_id']}`",
        "",
        "## Sufficiency",
    ]
    lines.extend(_kv(report["sufficiency"]))
    lines.extend(["", "## Rule Selectability"])
    lines.extend(_kv(report["selectability"]))
    lines.extend(["", report["warning"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _kv(values: dict[str, Any]) -> list[str]:
    return [f"- {key}: `{value}`" for key, value in values.items()]
