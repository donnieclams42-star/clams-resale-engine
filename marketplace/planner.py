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
    due_targets_for_market,
    finish_run,
    list_targets,
    mark_run_started,
    record_target_failure,
    row_to_target,
    running_discovery_run,
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
    try:
        from dealbrain.spend import can_start_facebook_run
        from marketplace.catalog import ESTIMATED_APIFY_USD_PER_RUN
        leftover = str(getattr(target, "cadence_tier", "") or "").upper() in {"RESEARCH", "REMOTE_RESEARCH"}
        ok, reason, meta = can_start_facebook_run(ESTIMATED_APIFY_USD_PER_RUN, leftover_research=leftover)
        if not ok and reason in {"apify_daily_cap", "facebook_daily_run_cap"}:
            spent = float((meta or {}).get("spent") or 0)
            return {
                "ok": False,
                "error": reason,
                "message": f"Facebook daily cap reached (${spent:.2f})",
                "spend_blocked": True,
                "scheduler_healthy": True,
            }
    except Exception:
        pass
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


CORE_MARKETS = ["south-jersey", "philadelphia"]
NORTH_MARKETS = ["trenton", "newark"]


def _rotate(groups: list[str]) -> list[str]:
    from dealbrain.spend import last_facebook_market
    last = last_facebook_market()
    if last in groups:
        start = (groups.index(last) + 1) % len(groups)
        return groups[start:] + groups[:start]
    return list(groups)


def _due(market_id: str, cadence: str = "", query_type: str = "", product_family: str = "", query: str = "") -> dict[str, Any]:
    rows = due_targets_for_market(
        market_id,
        limit=1,
        cadence=cadence,
        query_type=query_type,
        product_family=product_family,
        query=query,
    )
    return rows[0] if rows else {}


def _pick_boost_target() -> dict[str, Any]:
    from dealbrain.budget import boost_targeting
    targeting = boost_targeting()
    if not targeting.get("active"):
        return {}
    family = str(targeting.get("family") or "")
    query_type = str(targeting.get("query_type") or "")
    query = str(targeting.get("query") or "")
    market = str(targeting.get("market") or "")
    cadence = {"REPAIR": "REPAIR", "TREASURE": "TREASURE", "GENERIC": "GENERIC", "RESEARCH": "RESEARCH"}.get(query_type.upper(), "")
    markets = [market] if market else CORE_MARKETS + NORTH_MARKETS
    for market_id in markets:
        row = _due(market_id, cadence=cadence, query_type=query_type, product_family=family, query=query)
        if row:
            return row
        if family:
            row = _due(market_id, product_family=family)
            if row and str(row.get("cadence_tier") or "").upper() != "RESEARCH":
                return row
        if query:
            row = _due(market_id, query=query)
            if row and str(row.get("cadence_tier") or "").upper() != "RESEARCH":
                return row
    return {}


def _pick_lane(lane: str, *, runs_today: int = 0) -> dict[str, Any]:
    if lane == "BOOST":
        return _pick_boost_target()
    if lane == "CORE_PRECISION":
        for market_id in _rotate(CORE_MARKETS):
            row = _due(market_id, cadence="PRECISION")
            if row:
                return row
        return {}
    if lane == "CORE_REPAIR":
        for market_id in _rotate(CORE_MARKETS):
            row = _due(market_id, cadence="REPAIR")
            if row:
                return row
        return {}
    if lane == "NORTH_PRECISION":
        for market_id in _rotate(NORTH_MARKETS):
            row = _due(market_id, cadence="PRECISION")
            if row:
                return row
        return {}
    if lane == "LOCAL_TREASURE":
        # Same slot budget as before. Alternate treasure/generic so generic is not starved
        # when treasure targets stay perpetually due.
        prefer_generic = (int(runs_today or 0) // 6) % 2 == 1
        cadences = ("GENERIC", "TREASURE") if prefer_generic else ("TREASURE", "GENERIC")
        for cadence in cadences:
            for market_id in _rotate(CORE_MARKETS + NORTH_MARKETS):
                row = _due(market_id, cadence=cadence)
                if row:
                    return row
        return {}
    return {}


def _next_staggered_target(protect_core: bool = False, skipped: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    from dealbrain.budget import facebook_run_priority_lanes, boost_targeting
    from dealbrain.spend import facebook_runs_today
    from marketplace.catalog import LEVEL1_PROTECTED_MARKET_IDS

    skipped = skipped if skipped is not None else []
    runs = 0
    try:
        runs = facebook_runs_today()
    except Exception:
        runs = 0
    targeting = {}
    extra = False
    try:
        targeting = boost_targeting()
        extra = bool(targeting.get("active")) and runs >= 30
    except Exception:
        extra = False
    lanes = facebook_run_priority_lanes(protect_core=protect_core, runs_today=runs, extra_budget=extra)
    for lane in lanes:
        row = _pick_lane(lane, runs_today=runs)
        if row:
            if protect_core and str(row.get("market_id") or "") not in LEVEL1_PROTECTED_MARKET_IDS:
                skipped.append({"lane": lane, "reason": "precision protected"})
                continue
            if str(row.get("cadence_tier") or "").upper() == "RESEARCH":
                skipped.append({"lane": lane, "reason": "remote blocked by leftover-only rule"})
                continue
            return row
        skipped.append({"lane": lane, "reason": "cadence not due"})
    if protect_core:
        return {}
    fallback = due_targets(limit=8)
    for row in fallback:
        if str(row.get("cadence_tier") or "").upper() == "RESEARCH":
            skipped.append({"lane": "REMOTE_RESEARCH", "reason": "remote leftover-only"})
            continue
        return row
    return {}


async def planner_tick(config: MarketplaceConfig | None = None) -> dict[str, Any]:
    cfg = config or get_config()
    if not cfg.scanner_enabled or not cfg.scheduler_enabled:
        return {"ok": True, "skipped": True, "reason": "scheduler_disabled", "scheduler_healthy": True}
    if not cfg.apify_configured and cfg.primary_provider != "mock":
        return {"ok": True, "skipped": True, "reason": "not_configured", "scheduler_healthy": True}
    if cfg.allow_fallback:
        cfg = replace(cfg, allow_fallback=False)
    if running_discovery_run():
        return {"ok": True, "skipped": True, "reason": "run_in_flight", "scheduler_healthy": True}
    from marketplace.catalog import ESTIMATED_APIFY_USD_PER_RUN, LEVEL1_PROTECTED_MARKET_IDS
    from marketplace.ledger import cap_reason_label, cap_state_from_meta, lane_due_reason, record_scheduler_decision
    mark_facebook_level1_start = None
    ok, reason, meta = True, "ok", {}
    try:
        from dealbrain.spend import can_start_facebook_run, mark_facebook_level1_start as _mark_start
        mark_facebook_level1_start = _mark_start
        ok, reason, meta = can_start_facebook_run(ESTIMATED_APIFY_USD_PER_RUN)
        state = cap_state_from_meta(meta, ok=ok, reason=reason)
        if not ok:
            logger.info("MARKETPLACE_PLANNER_BLOCKED reason=%s cap_state=%s", reason, state)
            record_scheduler_decision(
                reason_selected=cap_reason_label(reason),
                cap_state=state,
                launched=False,
                extra={"spend": meta, "reason_code": reason},
            )
            return {"ok": True, "skipped": True, "reason": reason, "spend": meta, "cap_state": state, "scheduler_healthy": True}
    except Exception:
        mark_facebook_level1_start = None
        ok, reason, meta = True, "ok", {}
        state = "CAP_OK"
    else:
        state = cap_state_from_meta(meta, ok=ok, reason=reason)
    protect = bool((meta or {}).get("protect_core_regions"))
    skipped_lanes: list[dict[str, Any]] = []
    row = _next_staggered_target(protect_core=protect, skipped=skipped_lanes)
    if not row:
        record_scheduler_decision(
            reason_selected=cap_reason_label("no_due_targets"),
            skipped=skipped_lanes,
            cap_state=state,
            launched=False,
        )
        return {"ok": True, "skipped": True, "reason": "no_due_targets", "cap_state": state, "scheduler_healthy": True}
    if protect and str(row.get("market_id") or "") not in LEVEL1_PROTECTED_MARKET_IDS:
        record_scheduler_decision(
            reason_selected=cap_reason_label("protect_core_regions"),
            skipped=skipped_lanes,
            cap_state=state,
            launched=False,
        )
        return {"ok": True, "skipped": True, "reason": "protect_core_regions", "cap_state": state, "scheduler_healthy": True}
    target = row_to_target(row)
    from marketplace.ledger import lane_for_target
    selected_lane = lane_for_target(row)
    jitter = random.randint(0, max(0, min(cfg.jitter_seconds, 8)))
    if jitter:
        logger.info("MARKETPLACE_PLANNER_JITTER target=%s seconds=%s", target.id, jitter)
    result = await start_target_run(target, config=cfg)
    launched = bool(result.get("ok"))
    record_scheduler_decision(
        selected_lane=selected_lane,
        selected_market=target.market_id,
        selected_query=target.query,
        reason_selected=lane_due_reason(selected_lane) if launched else str(result.get("error") or "start_failed"),
        skipped=skipped_lanes,
        cap_state=state,
        launched=launched,
        extra={"run_id": result.get("run_id") or ""},
    )
    if launched and mark_facebook_level1_start:
        try:
            mark_facebook_level1_start(target.market_id)
        except Exception:
            pass
    return {"ok": True, "started": [result], "stagger_market": target.market_id, "cap_state": state, "lane": selected_lane, "scheduler_healthy": True}


def _next_research_target() -> dict[str, Any]:
    from marketplace.catalog import LEVEL1_PROTECTED_MARKET_IDS
    from marketplace.store import due_targets
    rows = due_targets(limit=8)
    for row in rows:
        if str(row.get("cadence_tier") or "").upper() == "RESEARCH" and int(row.get("enabled") or 0) == 1:
            if str(row.get("market_id") or "") not in LEVEL1_PROTECTED_MARKET_IDS:
                return row
    return {}


async def planner_research_tick(config: MarketplaceConfig | None = None) -> dict[str, Any]:
    """Leftover-budget remote research. Never raises the $0.50 cap. Local hunting keeps the first 30 runs."""
    cfg = config or get_config()
    try:
        from dealbrain.spend import can_start_facebook_run
        from marketplace.catalog import ESTIMATED_APIFY_USD_PER_RUN
        ok, reason, meta = can_start_facebook_run(ESTIMATED_APIFY_USD_PER_RUN, leftover_research=True)
        if not ok:
            from marketplace.ledger import cap_reason_label, cap_state_from_meta, record_scheduler_decision
            record_scheduler_decision(
                selected_lane="REMOTE_RESEARCH",
                reason_selected=cap_reason_label(reason),
                cap_state=cap_state_from_meta(meta, ok=ok, reason=reason),
                launched=False,
                extra={"leftover_research": True, "reason_code": reason},
            )
            return {"ok": True, "skipped": True, "reason": reason, "spend": meta, "scheduler_healthy": True}
        row = _next_research_target()
        if not row:
            return {"ok": True, "skipped": True, "reason": "no_due_research_targets"}
        target = row_to_target(row)
        result = await start_target_run(target, config=cfg)
        from marketplace.ledger import record_scheduler_decision
        launched = bool(result.get("ok"))
        record_scheduler_decision(
            selected_lane="REMOTE_RESEARCH",
            selected_market=target.market_id,
            selected_query=target.query,
            reason_selected="remote leftover-only due" if launched else str(result.get("error") or "start_failed"),
            launched=launched,
            extra={"leftover_research": True, "run_id": result.get("run_id") or ""},
        )
        return {"ok": True, "started": [result], "research_market": target.market_id, "scheduler_healthy": True}
    except Exception:
        return {"ok": True, "skipped": True, "reason": "research_tick_error"}
