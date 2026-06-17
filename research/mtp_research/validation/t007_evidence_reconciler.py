from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


FORBIDDEN_RPC_ATTRIBUTES = (
    "sendTransaction",
    "signTransaction",
    "sign_message",
    "private_key",
    "secret_key",
    "keypair",
    "wallet",
)


class ForbiddenReconciliationOperation(RuntimeError):
    pass


@dataclass(frozen=True)
class ReconciliationConfig:
    run_root: Path | str
    signatures: list[str] = field(default_factory=list)
    enable_rpc: bool = False
    max_signatures: int = 100


def _check_read_only_client(rpc_client: Any) -> None:
    names = {name.lower(): name for name in dir(rpc_client)}
    for forbidden in FORBIDDEN_RPC_ATTRIBUTES:
        if forbidden.lower() in names:
            raise ForbiddenReconciliationOperation(f"forbidden RPC/client attribute: {names[forbidden.lower()]}")


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def run_t007_evidence_reconciliation(config: ReconciliationConfig, *, rpc_client: Any | None = None) -> dict[str, Any]:
    root = Path(config.run_root)
    root.mkdir(parents=True, exist_ok=True)
    signatures = list(dict.fromkeys(config.signatures))
    if rpc_client is not None and not config.enable_rpc:
        raise ValueError("enable_rpc must be true for read-only RPC reconstruction")
    if config.enable_rpc and int(config.max_signatures or 0) <= 0:
        raise ValueError("max_signatures must be positive when enable_rpc is true")
    if rpc_client is not None:
        _check_read_only_client(rpc_client)

    inspected = signatures[: max(0, int(config.max_signatures))]
    findings = 0
    for signature in inspected:
        tx = None
        status = "local_context_only"
        if config.enable_rpc and rpc_client is not None:
            getter = getattr(rpc_client, "get_transaction", None) or getattr(rpc_client, "getTransaction", None)
            if getter is not None:
                tx = getter(signature)
                status = "rpc_transaction_fetched" if tx is not None else "rpc_transaction_missing"
        _append_jsonl(
            root / "reconciliation_findings.jsonl",
            {
                "signature": signature,
                "status": status,
                "has_transaction_context": tx is not None,
                "read_only": True,
            },
        )
        findings += 1

    summary = {
        "rpc_enabled": bool(config.enable_rpc),
        "inspected_signatures": len(inspected),
        "candidate_signatures": len(signatures),
        "max_signatures": int(config.max_signatures),
        "findings_written": findings,
        "trading_enabled": False,
        "paper_trading_enabled": False,
        "wallet_signing_enabled": False,
    }
    (root / "reconciliation_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary
