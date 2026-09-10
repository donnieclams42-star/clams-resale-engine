from __future__ import annotations

import os
from dataclasses import dataclass


def env_str(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(float(os.getenv(name, str(default)) or default))
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)) or default)
    except Exception:
        return default


@dataclass
class MarketplaceConfig:
    apify_token: str
    webhook_secret: str
    primary_provider: str
    rigel_actor: str
    k1ra_actor: str
    discovery_hot_task_id: str
    discovery_normal_task_id: str
    detail_task_id: str
    fallback_task_id: str
    scanner_enabled: bool
    scheduler_enabled: bool
    provider_rigel_enabled: bool
    provider_k1ra_enabled: bool
    allow_fallback: bool
    public_base_url: str
    max_items_discovery: int
    max_items_canary: int
    stage2_max_per_run: int
    circuit_breaker_failures: int
    circuit_retry_seconds: int
    recovery_stale_seconds: int
    recovery_interval_seconds: int
    planner_interval_seconds: int
    jitter_seconds: int
    seen_duplicate_hours: int
    default_currency: str
    default_country: str

    @property
    def apify_configured(self) -> bool:
        return bool(self.apify_token)

    @property
    def webhook_configured(self) -> bool:
        return bool(self.webhook_secret)

    def actor_for(self, provider: str) -> str:
        name = (provider or self.primary_provider or "rigelbytes").strip().lower()
        if name in {"k1ra", "k1ra_marketplace"}:
            return self.k1ra_actor
        return self.rigel_actor

    def task_id_for(self, *, cadence_tier: str = "NORMAL", stage: str = "discovery", provider: str = "") -> str:
        name = (provider or self.primary_provider or "").strip().lower()
        stage_l = (stage or "discovery").strip().lower()
        if stage_l == "detail" and self.detail_task_id:
            return self.detail_task_id
        if name in {"k1ra", "k1ra_marketplace"} and self.fallback_task_id:
            return self.fallback_task_id
        tier = (cadence_tier or "NORMAL").strip().upper()
        if tier == "HOT" and self.discovery_hot_task_id:
            return self.discovery_hot_task_id
        if self.discovery_normal_task_id:
            return self.discovery_normal_task_id
        return ""


def _scheduler_enabled() -> bool:
    if os.getenv("MARKETPLACE_ENABLE_SCHEDULER") is not None:
        return env_bool("MARKETPLACE_ENABLE_SCHEDULER", False)
    return env_bool("MARKETPLACE_SCANNER_SCHEDULER", False)


def get_config() -> MarketplaceConfig:
    return MarketplaceConfig(
        apify_token=env_str("APIFY_API_TOKEN") or env_str("APIFY_TOKEN"),
        webhook_secret=env_str("APIFY_WEBHOOK_SECRET"),
        primary_provider=env_str("MARKET_RADAR_FB_PROVIDER", "rigelbytes").lower() or "rigelbytes",
        rigel_actor=env_str("APIFY_FB_RIGEL_ACTOR", "rigelbytes/facebook-marketplace"),
        k1ra_actor=env_str("APIFY_FB_K1RA_ACTOR", "k1ra/facebook-marketplace-scraper"),
        discovery_hot_task_id=env_str("APIFY_FB_DISCOVERY_HOT_TASK_ID"),
        discovery_normal_task_id=env_str("APIFY_FB_DISCOVERY_NORMAL_TASK_ID"),
        detail_task_id=env_str("APIFY_FB_DETAIL_TASK_ID"),
        fallback_task_id=env_str("APIFY_FB_FALLBACK_TASK_ID"),
        scanner_enabled=env_bool("MARKETPLACE_SCANNER_ENABLED", True),
        scheduler_enabled=_scheduler_enabled(),
        provider_rigel_enabled=env_bool("MARKETPLACE_PROVIDER_RIGEL_ENABLED", True),
        provider_k1ra_enabled=env_bool("MARKETPLACE_PROVIDER_K1RA_ENABLED", True),
        allow_fallback=env_bool("MARKETPLACE_ALLOW_FALLBACK", False),
        public_base_url=env_str("APP_BASE_URL") or env_str("BASE_URL") or env_str("PUBLIC_BASE_URL") or "https://market-radar.fly.dev",
        max_items_discovery=env_int("MARKETPLACE_MAX_ITEMS_DISCOVERY", 12),
        max_items_canary=env_int("MARKETPLACE_MAX_ITEMS_CANARY", 8),
        stage2_max_per_run=env_int("MARKETPLACE_STAGE2_MAX_PER_RUN", 3),
        circuit_breaker_failures=env_int("MARKETPLACE_CIRCUIT_BREAKER_FAILURES", 3),
        circuit_retry_seconds=env_int("MARKETPLACE_CIRCUIT_RETRY_SECONDS", 21600),
        recovery_stale_seconds=env_int("MARKETPLACE_RECOVERY_STALE_SECONDS", 900),
        recovery_interval_seconds=env_int("MARKETPLACE_RECOVERY_INTERVAL_SECONDS", 120),
        planner_interval_seconds=env_int("MARKETPLACE_PLANNER_INTERVAL_SECONDS", 30),
        jitter_seconds=env_int("MARKETPLACE_JITTER_SECONDS", 20),
        seen_duplicate_hours=env_int("MARKETPLACE_SEEN_DUPLICATE_HOURS", 6),
        default_currency=env_str("MARKETPLACE_DEFAULT_CURRENCY", "USD") or "USD",
        default_country=env_str("MARKETPLACE_DEFAULT_COUNTRY", "US") or "US",
    )
