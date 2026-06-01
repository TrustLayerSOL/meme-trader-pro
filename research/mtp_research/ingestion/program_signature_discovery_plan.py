"""Program-signature discovery planning for broad launch cohorts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ProgramSignatureDiscoveryTarget:
    name: str
    program_id: str
    venue: str
    expected_event_type: str
    priority: int
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ProgramSignatureDiscoveryPlan:
    created_at: str
    targets: list[ProgramSignatureDiscoveryTarget]
    warning_flags: list[str] = field(default_factory=list)
    recommended_probe_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "targets": [target.to_dict() for target in self.targets],
            "warning_flags": self.warning_flags,
            "recommended_probe_command": self.recommended_probe_command,
        }


def build_default_program_signature_discovery_plan() -> ProgramSignatureDiscoveryPlan:
    targets = [
        ProgramSignatureDiscoveryTarget(
            name="pump_fun_token_creation",
            program_id="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
            venue="pumpfun",
            expected_event_type="bonding_curve_or_token_creation",
            priority=1,
            notes="Best candidate for failures before DexScreener visibility; probe signatures before hydrating transactions.",
        ),
        ProgramSignatureDiscoveryTarget(
            name="pumpswap_pool_creation",
            program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
            venue="pumpswap",
            expected_event_type="pool_creation_or_first_pool_trade",
            priority=2,
            notes="Useful for post-bonding-curve pools and early lifecycle trades; may miss tokens that die on Pump.fun.",
        ),
        ProgramSignatureDiscoveryTarget(
            name="raydium_launchlab_pool_creation",
            program_id="LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",
            venue="raydium_launchlab",
            expected_event_type="launchlab_pool_creation",
            priority=3,
            notes="Candidate Raydium launch source; program ID should be verified with tiny probes before scaling.",
        ),
        ProgramSignatureDiscoveryTarget(
            name="raydium_cpmm_pool_creation",
            program_id="CPMMoo8L3F4NbTegBCKVNuxFYvWzqMe9J1KLcXxj3xV",
            venue="raydium_cpmm",
            expected_event_type="pool_creation",
            priority=4,
            notes="Secondary Raydium pool source; likely biased toward tokens that reach DEX liquidity.",
        ),
    ]
    return ProgramSignatureDiscoveryPlan(
        created_at=datetime.now(timezone.utc).isoformat(),
        targets=targets,
        warning_flags=["dry_run_default_no_network_calls", "program_ids_require_probe_verification"],
        recommended_probe_command=(
            "./trading_env/bin/python -m research.mtp_research.ingestion.run_program_signature_probe "
            "--program-id 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P --limit 10 --execute"
        ),
    )
