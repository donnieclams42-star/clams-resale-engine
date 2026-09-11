from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


CADENCE_SECONDS = {
    "HOT": 5 * 60,
    "NORMAL": 15 * 60,
    "PRECISION": 40 * 60,
    "TREASURE": 3 * 60 * 60,
    "LOW": 3 * 60 * 60,
}


@dataclass
class ScanTarget:
    id: str
    name: str
    enabled: bool = True
    provider: str = "rigelbytes"
    query: str = ""
    product_family: str = ""
    query_type: str = "GENERIC"
    market_id: str = ""
    location: str = ""
    radius_miles: int = 40
    radius_km: int = 64
    currency: str = "USD"
    country: str = "US"
    cadence_tier: str = "NORMAL"
    result_limit: int = 12
    minimum_price: Optional[float] = None
    maximum_price: Optional[float] = None
    condition: str = ""
    delivery: str = ""
    listing_age_days: Optional[int] = None
    last_started_at: str = ""
    last_success_at: str = ""
    next_due_at: str = ""
    consecutive_failures: int = 0
    cost_budget: float = 0.0
    priority: int = 100
    health_status: str = "idle"
    is_canary: bool = False
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    def cadence_seconds(self) -> int:
        return CADENCE_SECONDS.get((self.cadence_tier or "NORMAL").upper(), CADENCE_SECONDS["NORMAL"])

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ListingRef:
    source: str
    source_listing_id: str
    canonical_url: str
    title: str = ""
    provider: str = ""


@dataclass
class ProviderRun:
    ok: bool
    run_id: str = ""
    dataset_id: str = ""
    status: str = "READY"
    provider: str = ""
    actor: str = ""
    task_id: str = ""
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderRunStatus:
    ok: bool
    run_id: str = ""
    status: str = ""
    dataset_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    usage_usd: Optional[float] = None
    item_count: Optional[int] = None
    error: str = ""
    terminal: bool = False
    succeeded: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


TERMINAL_OK = {"SUCCEEDED"}
TERMINAL_FAIL = {"FAILED", "TIMED-OUT", "ABORTED", "TIMED_OUT", "ABORT"}
TERMINAL_ALL = TERMINAL_OK | TERMINAL_FAIL
RUNNING_STATUSES = {"READY", "RUNNING", "CREATED", "PENDING"}
