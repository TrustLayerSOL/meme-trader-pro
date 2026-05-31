"""Plan bounded backfill targets from launch candidates."""

from __future__ import annotations

from research.mtp_research.ingestion.backfill_jobs import BackfillTarget, make_target_id
from research.mtp_research.ingestion.models import LaunchCandidate


class BackfillTargetPlanner:
    """Create deterministic historical backfill targets without network calls."""

    def candidates_to_targets(
        self,
        candidates: list[LaunchCandidate],
        roles: list[str] | None = None,
    ) -> list[BackfillTarget]:
        targets: list[BackfillTarget] = []
        for candidate in candidates:
            targets.extend(self.candidate_to_targets(candidate, roles=roles))
        return self.dedupe_targets(targets)

    def candidate_to_targets(
        self,
        candidate: LaunchCandidate,
        roles: list[str] | None = None,
    ) -> list[BackfillTarget]:
        selected_roles = roles or ["mint", "pool", "creator"]
        targets: list[BackfillTarget] = []
        for role in selected_roles:
            for address in self._addresses_for_role(candidate, role):
                if not address:
                    continue
                targets.append(
                    BackfillTarget(
                        target_id=make_target_id(address, role, candidate.token_mint),
                        address=address,
                        role=role,
                        token_mint=candidate.token_mint,
                        source="candidate_registry",
                        metadata_json={
                            "candidate_source": candidate.source,
                            "candidate_venue": candidate.venue,
                            "pool_address": candidate.pool_address,
                            "creator_wallet": candidate.creator_wallet,
                        },
                    )
                )
        return targets

    def dedupe_targets(self, targets: list[BackfillTarget]) -> list[BackfillTarget]:
        by_id = {}
        for target in targets:
            by_id.setdefault(target.target_id, target)
        return [by_id[target_id] for target_id in sorted(by_id)]

    def _addresses_for_role(self, candidate: LaunchCandidate, role: str) -> list[str]:
        if role == "mint":
            return [candidate.token_mint]
        if role == "pool":
            return [candidate.pool_address] if candidate.pool_address else []
        if role == "creator":
            return [candidate.creator_wallet] if candidate.creator_wallet else []
        if role == "wallet":
            wallets = candidate.metadata_json.get("wallets", [])
            return [str(wallet) for wallet in wallets if wallet]
        return []
