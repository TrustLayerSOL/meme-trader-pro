"""Compare ungated and price-quality-gated diagnostic validation artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from research.mtp_research.validation.research_dataset_store import ResearchDatasetStore


def build_price_quality_validation_comparison(
    ungated_dataset_path: Path | str,
    gated_dataset_path: Path | str,
    ungated_fold_json_path: Path | str | None = None,
    gated_fold_json_path: Path | str | None = None,
    ungated_robust_json_path: Path | str | None = None,
    gated_robust_json_path: Path | str | None = None,
) -> dict[str, Any]:
    ungated_rows = ResearchDatasetStore(ungated_dataset_path).load_all()
    gated_rows = ResearchDatasetStore(gated_dataset_path).load_all()
    ungated_fold = _load_json(ungated_fold_json_path)
    gated_fold = _load_json(gated_fold_json_path)
    ungated_robust = _load_json(ungated_robust_json_path)
    gated_robust = _load_json(gated_robust_json_path)

    ungated_row_count = len(ungated_rows)
    gated_row_count = len(gated_rows)
    ungated_tokens = {row.token_mint for row in ungated_rows}
    gated_tokens = {row.token_mint for row in gated_rows}
    ungated_fold_count = _valid_fold_count(ungated_fold)
    gated_fold_count = _valid_fold_count(gated_fold)
    ungated_selected = _selected_trade_count(ungated_fold)
    gated_selected = _selected_trade_count(gated_fold)
    rule_changes = _rule_metric_changes(ungated_robust, gated_robust)
    row_loss = ungated_row_count - gated_row_count
    token_loss = len(ungated_tokens) - len(gated_tokens)
    fold_loss = ungated_fold_count - gated_fold_count
    selected_loss = ungated_selected - gated_selected

    return {
        "report_id": _report_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ungated_dataset_path": str(ungated_dataset_path),
        "gated_dataset_path": str(gated_dataset_path),
        "ungated_row_count": ungated_row_count,
        "gated_row_count": gated_row_count,
        "row_loss_count": row_loss,
        "row_loss_rate": (row_loss / ungated_row_count) if ungated_row_count else None,
        "ungated_token_count": len(ungated_tokens),
        "gated_token_count": len(gated_tokens),
        "token_loss_count": token_loss,
        "token_loss_rate": (token_loss / len(ungated_tokens)) if ungated_tokens else None,
        "ungated_valid_fold_count": ungated_fold_count,
        "gated_valid_fold_count": gated_fold_count,
        "fold_loss_count": fold_loss,
        "ungated_selected_trade_count": ungated_selected,
        "gated_selected_trade_count": gated_selected,
        "selected_trade_loss_count": selected_loss,
        "rule_metric_changes": rule_changes,
        "outlier_dependence_improved": _outlier_dependence_improved(rule_changes),
        "recommended_next_action": _recommend(row_loss, ungated_row_count, gated_fold_count, rule_changes),
        "warning_flags": ["diagnostic_only_not_trading_signal"],
    }


def write_comparison_json(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_comparison_markdown(report: dict[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Price Quality Validation Comparison",
        "",
        "> Warning: Price-quality comparison is diagnostic only. It is not a trading signal.",
        "",
        f"- Report ID: `{report.get('report_id')}`",
        f"- Recommended next action: `{report.get('recommended_next_action', 'unknown')}`",
        "",
        "| Metric | Ungated | Gated | Loss |",
        "| --- | ---: | ---: | ---: |",
        f"| Rows | {report.get('ungated_row_count', '')} | {report.get('gated_row_count', '')} | {report.get('row_loss_count', '')} |",
        f"| Tokens | {report.get('ungated_token_count', '')} | {report.get('gated_token_count', '')} | {report.get('token_loss_count', '')} |",
        f"| Valid folds | {report.get('ungated_valid_fold_count', '')} | {report.get('gated_valid_fold_count', '')} | {report.get('fold_loss_count', '')} |",
        f"| Selected trades | {report.get('ungated_selected_trade_count', '')} | {report.get('gated_selected_trade_count', '')} | {report.get('selected_trade_loss_count', '')} |",
        "",
        "## Rule Metric Changes",
        "",
        "| Rule | Ungated Median | Gated Median | Ungated Capped Mean | Gated Capped Mean |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for rule_id, change in report.get("rule_metric_changes", {}).items():
        lines.append(
            f"| `{rule_id}` | {_fmt(change.get('ungated_median'))} | {_fmt(change.get('gated_median'))} | "
            f"{_fmt(change.get('ungated_capped_mean'))} | {_fmt(change.get('gated_capped_mean'))} |"
        )
    lines.extend(["", "## Warnings", "", *[f"- `{flag}`" for flag in report.get("warning_flags", [])], ""])
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _load_json(path: Path | str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _valid_fold_count(report: dict[str, Any]) -> int:
    return sum(int(item.get("valid_fold_count", 0) or 0) for item in report.get("config_results", []))


def _selected_trade_count(report: dict[str, Any]) -> int:
    total = 0
    for config in report.get("config_results", []):
        for rule in config.get("rule_sufficiency", []):
            total += int(rule.get("total_test_selected_count", 0) or 0)
    return total


def _rule_metric_changes(ungated: dict[str, Any], gated: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ungated_by_rule = {item.get("rule_id"): item for item in ungated.get("rule_summaries", [])}
    gated_by_rule = {item.get("rule_id"): item for item in gated.get("rule_summaries", [])}
    output: dict[str, dict[str, Any]] = {}
    for rule_id in sorted(set(ungated_by_rule) | set(gated_by_rule)):
        before = ungated_by_rule.get(rule_id, {})
        after = gated_by_rule.get(rule_id, {})
        output[str(rule_id)] = {
            "ungated_selected_count": before.get("selected_count"),
            "gated_selected_count": after.get("selected_count"),
            "ungated_median": _nested(before, "raw_metrics", "median") or _nested(before, "robust_returns", "median"),
            "gated_median": _nested(after, "raw_metrics", "median") or _nested(after, "robust_returns", "median"),
            "ungated_capped_mean": _nested(before, "capped_metrics", "mean"),
            "gated_capped_mean": _nested(after, "capped_metrics", "mean"),
        }
    return output


def _nested(payload: dict[str, Any], *keys: str):
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _outlier_dependence_improved(rule_changes: dict[str, dict[str, Any]]) -> bool:
    for change in rule_changes.values():
        before = change.get("ungated_capped_mean")
        after = change.get("gated_capped_mean")
        if before is not None and after is not None and abs(after) < abs(before):
            return True
    return False


def _recommend(
    row_loss: int,
    ungated_rows: int,
    gated_fold_count: int,
    rule_changes: dict[str, dict[str, Any]],
) -> str:
    row_loss_rate = (row_loss / ungated_rows) if ungated_rows else 0
    if gated_fold_count == 0 or row_loss_rate > 0.9:
        return "improve_price_inference_before_rule_review"
    if not rule_changes:
        return "rerun_gated_rule_reports"
    return "review_gated_rule_metrics_before_scaling"


def _report_id() -> str:
    created = datetime.now(timezone.utc).isoformat()
    digest = sha256(f"price_quality_validation_comparison|{created}".encode("utf-8")).hexdigest()[:16]
    return f"price_quality_validation_comparison_{digest}"


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)
