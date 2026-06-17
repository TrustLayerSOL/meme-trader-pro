from __future__ import annotations

from pathlib import Path

import pytest

from research.mtp_research.validation.t007_evidence_reconciler import (
    ForbiddenReconciliationOperation,
    ReconciliationConfig,
    run_t007_evidence_reconciliation,
)


def test_read_only_rpc_mode_requires_explicit_flag(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="enable_rpc"):
        run_t007_evidence_reconciliation(
            ReconciliationConfig(run_root=tmp_path, signatures=["sig-a"], enable_rpc=False),
            rpc_client=object(),
        )


def test_rpc_mode_requires_signature_cap(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_signatures"):
        run_t007_evidence_reconciliation(
            ReconciliationConfig(run_root=tmp_path, signatures=["sig-a"], enable_rpc=True, max_signatures=0),
            rpc_client=object(),
        )


def test_reconciler_enforces_max_signatures_and_writes_findings(tmp_path: Path) -> None:
    class FakeRpc:
        def get_transaction(self, signature: str) -> dict:
            return {"signature": signature, "meta": {"err": None}}

    result = run_t007_evidence_reconciliation(
        ReconciliationConfig(run_root=tmp_path, signatures=["sig-a", "sig-b"], enable_rpc=True, max_signatures=1),
        rpc_client=FakeRpc(),
    )

    assert result["inspected_signatures"] == 1
    assert result["rpc_enabled"] is True
    assert result["findings_written"] == 1
    assert (tmp_path / "reconciliation_findings.jsonl").exists()
    assert (tmp_path / "reconciliation_summary.json").exists()


def test_reconciler_blocks_wallet_or_signing_clients(tmp_path: Path) -> None:
    class BadRpc:
        def sendTransaction(self) -> None:
            raise AssertionError("must not be called")

    with pytest.raises(ForbiddenReconciliationOperation):
        run_t007_evidence_reconciliation(
            ReconciliationConfig(run_root=tmp_path, signatures=["sig-a"], enable_rpc=True, max_signatures=1),
            rpc_client=BadRpc(),
        )
