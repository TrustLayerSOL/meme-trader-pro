from __future__ import annotations

import time
from pathlib import Path

from research.mtp_research.validation.no_laserstream_lifecycle_collector import (
    NoLaserstreamHydrationQueue,
    run_no_laserstream_lifecycle_smoke,
    write_no_laserstream_bottleneck_audit,
)
from research.mtp_research.validation.official_lifecycle_watch import OfficialLifecycleConfig


class FakeLogSource:
    def __init__(self, logs: list[dict]) -> None:
        self.logs = [dict(row) for row in logs]
        self.fetch_calls = 0
        self.requests_used = 0

    def availability(self) -> dict:
        return {"available": True, "source": "fake_logs"}

    def fetch_logs(self, *, limit: int) -> list[dict]:
        self.fetch_calls += 1
        rows = self.logs[:limit]
        self.logs = self.logs[limit:]
        return rows

    def close(self) -> None:
        return None


class FakeHydrator:
    def __init__(self, candidates: dict[str, dict], delays: dict[str, float] | None = None) -> None:
        self.candidates = {key: dict(value) for key, value in candidates.items()}
        self.delays = delays or {}
        self.requests_used = 0

    def hydrate(self, provisional: dict) -> dict:
        signature = provisional["signature"]
        delay = self.delays.get(signature, 0.0)
        if delay:
            time.sleep(delay)
        self.requests_used += 1
        observed = float(provisional.get("log_observed_at") or 0)
        candidate = self.candidates.get(signature)
        if candidate is None:
            return {
                "signature": signature,
                "hydration_status": "hydrated_not_create",
                "hydration_completed_at": observed + delay,
                "missing_reason": "fake_not_create",
            }
        synthetic_hydration_delay = float(candidate.get("synthetic_hydration_delay_seconds", delay + 0.2))
        return {
            "signature": signature,
            "hydration_status": "hydrated_create_confirmed",
            "hydration_completed_at": observed + synthetic_hydration_delay,
            "candidate": dict(candidate),
            "mint": candidate.get("mint"),
            "creator": candidate.get("creator"),
            "bonding_curve": candidate.get("bonding_curve"),
            "associated_bonding_curve": candidate.get("associated_bonding_curve"),
            "parse_confidence": candidate.get("parse_confidence", "high"),
        }


class FakeFetcher:
    def __init__(self, events_by_mint: dict[str, list[dict]] | None = None) -> None:
        self.events_by_mint = {key: [dict(row) for row in value] for key, value in (events_by_mint or {}).items()}
        self.requests_used = 0
        self.raw_transactions: list[dict] = []
        self.calls: list[tuple[str, list[str]]] = []

    def fetch_for_mint(
        self,
        mint: str,
        *,
        signatures_per_mint: int,
        transactions_per_mint: int,
        followup_addresses: list[str] | None = None,
    ) -> list[dict]:
        self.requests_used += 1
        self.calls.append((mint, list(followup_addresses or [])))
        return [dict(row) for row in self.events_by_mint.get(mint, [])[:transactions_per_mint]]


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            import json

            rows.append(json.loads(line))
    return rows


def test_writes_provisional_birth_before_hydration_result(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path, max_birth_to_first_followup_seconds=5.0)
    source = FakeLogSource(
        [
            {
                "signature": "sig-a",
                "program_id": "pumpfun",
                "log_observed_at": 100.0,
                "slot": 7,
                "source_adapter": "fake_no_laserstream_logs",
            }
        ]
    )
    hydrator = FakeHydrator(
        {
            "sig-a": {
                "mint": "mint-a",
                "creator": "creator-a",
                "bonding_curve": "curve-a",
                "associated_bonding_curve": "assoc-a",
                "launch_time": 99.5,
            }
        }
    )
    fetcher = FakeFetcher({"mint-a": [{"mint": "mint-a", "timestamp": 101.0, "fdv_proxy": 9000.0}]})

    result = run_no_laserstream_lifecycle_smoke(
        config,
        target_births=1,
        execute=True,
        source=source,
        hydrator=hydrator,
        fetcher=fetcher,
        now_fn=iter([100.5, 101.0, 101.1, 101.2, 101.3]).__next__,
        max_runtime_seconds=2,
    )

    provisional = read_jsonl(config.provisional_births_path)
    hydration = read_jsonl(config.hydration_results_path)
    births = read_jsonl(config.births_path)

    assert result["official_accepted_births"] == 1
    assert provisional[0]["hydration_status"] == "pending_hydration"
    assert hydration[0]["hydration_status"] == "hydrated_create_confirmed"
    assert births[0]["mint"] == "mint-a"
    assert births[0]["create_log_freshness_accepted"] is True
    assert births[0]["hydration_freshness_accepted"] is True
    assert births[0]["fdv_path_before_10k"] is True
    assert births[0]["fdv_path_before_20k"] is True
    assert births[0]["observed_to_first_followup_seconds"] <= 5.0


def test_hydration_queue_streams_fast_result_before_slow_result() -> None:
    hydrator = FakeHydrator(
        {
            "slow": {"mint": "mint-slow"},
            "fast": {"mint": "mint-fast"},
        },
        delays={"slow": 0.2, "fast": 0.0},
    )
    queue = NoLaserstreamHydrationQueue(hydrator=hydrator, max_workers=2, hydration_timeout_seconds=5)
    queue.submit({"signature": "slow", "provisional_birth_id": "birth-slow"})
    queue.submit({"signature": "fast", "provisional_birth_id": "birth-fast"})

    deadline = time.monotonic() + 1
    first: list[dict] = []
    while time.monotonic() < deadline and not first:
        first = queue.drain_completed(limit=1)
        time.sleep(0.01)

    assert first
    assert first[0]["signature"] == "fast"
    assert first[0]["mint"] == "mint-fast"
    queue.close()


def test_late_hydration_still_creates_official_birth_but_fails_hydration_gate(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path, max_birth_to_first_followup_seconds=5.0)
    source = FakeLogSource([{"signature": "sig-late", "log_observed_at": 100.0}])
    hydrator = FakeHydrator(
        {"sig-late": {"mint": "mint-late", "launch_time": 100.0, "synthetic_hydration_delay_seconds": 6.2}}
    )
    fetcher = FakeFetcher()

    result = run_no_laserstream_lifecycle_smoke(
        config,
        target_births=1,
        execute=True,
        source=source,
        hydrator=hydrator,
        fetcher=fetcher,
        now_fn=iter([106.1, 106.2, 106.3, 106.4]).__next__,
        max_runtime_seconds=1,
    )

    assert result["official_accepted_births"] == 1
    births = read_jsonl(config.births_path)
    assert births[0]["mint"] == "mint-late"
    assert births[0]["create_log_freshness_accepted"] is True
    assert births[0]["hydration_freshness_accepted"] is False
    assert births[0]["fdv_path_before_10k"] is False
    assert read_jsonl(config.stale_births_path) == []


def test_above_trigger_first_fdv_path_is_not_actionable_sample(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path, max_birth_to_first_followup_seconds=5.0)
    source = FakeLogSource([{"signature": "sig-hot", "log_observed_at": 100.0}])
    hydrator = FakeHydrator({"sig-hot": {"mint": "mint-hot", "launch_time": 100.0}})
    fetcher = FakeFetcher({"mint-hot": [{"mint": "mint-hot", "timestamp": 101.0, "fdv_proxy": 25_000.0}]})

    result = run_no_laserstream_lifecycle_smoke(
        config,
        target_births=1,
        execute=True,
        source=source,
        hydrator=hydrator,
        fetcher=fetcher,
        now_fn=iter([100.1, 100.2, 100.3, 100.4]).__next__,
        max_runtime_seconds=1,
    )

    assert result["official_accepted_births"] == 1
    assert result["crossed_20k"] == 1
    assert result["actionable_crossed_20k"] == 0
    births = read_jsonl(config.births_path)
    assert births[0]["fdv_path_before_10k"] is False
    assert births[0]["fdv_path_before_20k"] is False


def test_duplicate_signature_is_written_once(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    source = FakeLogSource(
        [
            {"signature": "sig-a", "log_observed_at": 100.0},
            {"signature": "sig-a", "log_observed_at": 100.1},
        ]
    )
    hydrator = FakeHydrator({"sig-a": {"mint": "mint-a", "launch_time": 100.0}})
    fetcher = FakeFetcher()

    result = run_no_laserstream_lifecycle_smoke(
        config,
        target_births=1,
        execute=True,
        source=source,
        hydrator=hydrator,
        fetcher=fetcher,
        now_fn=iter([101.0, 101.1, 101.2, 101.3]).__next__,
        max_runtime_seconds=1,
    )

    assert result["provisional_birth_logs"] == 1
    assert len(read_jsonl(config.provisional_births_path)) == 1


def test_bottleneck_audit_reports_hydration_registration_blocker(tmp_path: Path) -> None:
    config = OfficialLifecycleConfig(data_root=tmp_path)
    audit, paths = write_no_laserstream_bottleneck_audit(config)

    assert audit["current_v1_bottleneck"]["birth_registration_waits_for_hydration"] is True
    assert audit["v2_target_architecture"]["birth_registration_waits_for_hydration"] is False
    assert paths["json"].exists()
    assert paths["markdown"].exists()


def test_new_module_contains_no_execution_or_private_key_logic() -> None:
    module_path = Path("research/mtp_research/validation/no_laserstream_lifecycle_collector.py")
    text = module_path.read_text(encoding="utf-8").lower()
    forbidden = [
        "sendtransaction",
        "jupiter",
        "private_key",
        "secretkey",
        "wallet execution",
        "order routing",
    ]
    assert not any(term in text for term in forbidden)
