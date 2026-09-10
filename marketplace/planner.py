from __future__ import annotations

import logging
import random
from dataclasses import replace
from typing import Any

from marketplace.config import MarketplaceConfig, get_config
from marketplace.models import ScanTarget
from marketplace.providers.factory import get_provider, provider_enabled
from marketplace.store import (
    active_run_for_target,
    create_scan_run,
    due_targets,
    finish_run,
    list_targets,
    mark_run_started,
    record_target_failure,
    row_to_target,
)

logger = logging.getLogger("market_radar.marketplace")


def can_start_target(target: ScanTarget) -> tuple[bool, str]:
    if not target.enabled:
        return False, "target_disabled"
    if target.health_status == "paused" and target.next_due_at:
        # half-open is handled by due_targets once next_due_at arrives
        pass
    locked = active_run_for_target(target.id)
    if locked:
        return False, "run_locked"
    return True, "ok"


async def start_target_run(target: ScanTarget, *, config: MarketplaceConfig | None = None, stage: str = "discovery") -> dict[str, Any]:
    cfg = config or get_config()
    if not cfg.scanner_enabled:
        return {"ok": False, "error": "scanner_disabled", "message": "Marketplace Scanner paused"}
    if not provider_enabled(target.provider, cfg):
        return {"ok": False, "error": "provider_disabled", "message": "Marketplace provider disabled"}
    ok, reason = can_start_target(target)
    if not ok:
        return {"ok": False, "error": reason, "message": "Scan already running" if reason == "run_locked" else reason}
    try:
        provider = get_provider(target.provider, cfg)
    except Exception as exc:
        return {"ok": False, "error": "provider_disabled", "message": str(exc)}
    local_run_id = create_scan_run(target, stage=stage, provider=target.provider, actor=getattr(provider, "actor", ""))
    started = await provider.start_discovery_run(target)
    if not started.ok:
        finish_run(local_run_id, status="FAILED", error_code=started.status or "provider_error", error_message=started.error or "Marketplace provider error")
        record_target_failure(target.id, breaker=cfg.circuit_breaker_failures, retry_seconds=cfg.circuit_retry_seconds)
        return {"ok": False, "error": started.status or "provider_error", "message": started.error or "Marketplace provider error", "run_id": local_run_id}
    mark_run_started(local_run_id, apify_run_id=started.run_id, dataset_id=started.dataset_id, actor=started.actor, status=started.status or "RUNNING")
    logger.info("MARKETPLACE_TARGET_STARTED target=%s apify_run_id=%s", target.id, started.run_id)
    return {"ok": True, "run_id": local_run_id, "apify_run_id": started.run_id, "provider": target.provider, "query": target.query, "market_id": target.market_id}


def _canary_match(row: dict[str, Any], query: str, market_id: str) -> bool:
    if query:
        wanted = query.strip().lower()
        if str(row.get("query") or "").strip().lower() != wanted:
            return False
    if market_id:
        wanted = market_id.strip().lower().replace(" ", "-")
        market = str(row.get("market_id") or "").strip().lower()
        location = str(row.get("location") or "").strip().lower()
        name = str(row.get("name") or "").strip().lower()
        if wanted not in {market, location} and wanted not in location and wanted not in name and wanted.replace("-", " ") not in location:
            return False
    return True


async def start_canary_runs(
    config: MarketplaceConfig | None = None,
    comparison: bool = False,
    *,
    query: str = "",
    market_id: str = "",
    max_items: int = 0,
    max_starts: int = 5,
    stage2_max: int = 0,
    allow_fallback: bool | None = None,
) -> dict[str, Any]:
    cfg = config or get_config()
    if stage2_max:
        cfg = replace(cfg, stage2_max_per_run=int(stage2_max))
    if allow_fallback is False:
        cfg = replace(cfg, allow_fallback=False)
    provider_name = cfg.primary_provider if cfg.primary_provider != "mock" else "mock"
    started = []
    skipped = []
    targets = list_targets(canary_only=True, provider=provider_name)
    if not targets and provider_name == "mock":
        targets = list_targets(canary_only=True)
    if query or market_id:
        targets = [row for row in targets if _canary_match(row, query, market_id)]
        max_starts = min(max_starts, 1)
    for row in targets:
        target = row_to_target(row)
        target.enabled = True
        if max_items:
            target.result_limit = int(max_items)
        result = await start_target_run(target, config=cfg)
        if result.get("ok"):
            started.append(result)
        else:
            skipped.append(result)
        if len(started) >= max(1, int(max_starts or 5)):
            break
    use_fallback = cfg.allow_fallback if allow_fallback is None else bool(allow_fallback)
    if comparison and use_fallback:
        for row in list_targets(canary_only=True, provider="k1ra")[:2]:
            target = row_to_target(row)
            target.enabled = True
            result = await start_target_run(target, config=cfg)
            started.append(result) if result.get("ok") else skipped.append(result)
    return {"ok": True, "started": started, "skipped": skipped, "count": len(started)}


async def planner_tick(config: MarketplaceConfig | None = None) -> dict[str, Any]:
    cfg = config or get_config()
    if not cfg.scanner_enabled or not cfg.scheduler_enabled:
        return {"ok": True, "skipped": True, "reason": "scheduler_disabled"}
    if not cfg.apify_configured and cfg.primary_provider != "mock":
        return {"ok": True, "skipped": True, "reason": "not_configured"}
    started = []
    for row in due_targets(limit=1):
        target = row_to_target(row)
        jitter = random.randint(0, max(0, cfg.jitter_seconds))
        if jitter:
            logger.info("MARKETPLACE_PLANNER_JITTER target=%s seconds=%s", target.id, jitter)
        result = await start_target_run(target, config=cfg)
        started.append(result)
    return {"ok": True, "started": started}
