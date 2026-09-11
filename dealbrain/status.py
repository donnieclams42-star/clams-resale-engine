from __future__ import annotations

from typing import Any

from dealbrain.config import get_config, twilio_configured
from dealbrain.store import deal_counts, list_deal_feed
from marketplace.config import get_config as marketplace_config
from marketplace.status import scanner_status


def _level1_status(providers: dict[str, Any]) -> dict[str, Any]:
    cfg = get_config()
    ebay = str((providers.get("ebay_active") or {}).get("status") or "")
    ready = ebay in {"LIVE", "DEGRADED"} or cfg.ebay_sniper_enabled
    return {
        "status": "READY" if ready else "NOT READY",
        "enabled": bool(cfg.first_profit_live) and int(cfg.scale_level or 0) >= 1,
        "scale_level": cfg.scale_level,
        "max_fb_runs_per_day": cfg.level1_max_fb_runs_per_day,
        "max_ebay_calls_per_day": cfg.level1_max_ebay_calls_per_day,
        "max_stage2_per_day": cfg.level1_max_stage2_per_day,
        "max_provider_dollars_per_day": cfg.apify_daily_cap_usd(),
        "note": "First Profit Level 1 uses eBay active market + small Facebook precision scans. PriceCharting is on hold.",
    }


def dealbrain_status() -> dict[str, Any]:
    cfg = get_config()
    mp = marketplace_config()
    try:
        counts = deal_counts()
    except Exception:
        counts = {}
    last_ebay = counts.get("last_ebay_run") or {}
    ebay_state = "LIVE"
    ebay_message = "eBay Mega Sniper is ready"
    if not cfg.ebay_sniper_enabled:
        ebay_state = "PAUSED"
        ebay_message = "eBay sniper paused"
    elif str(last_ebay.get("status") or "") == "FAILED":
        ebay_state = "DEGRADED"
        ebay_message = "eBay sniper reported an error"
    elif str(last_ebay.get("status") or "") == "completed_zero":
        ebay_message = "Scan completed — 0 listings"
    elif not last_ebay:
        ebay_message = "eBay sniper is waiting for the first scan"
    from dealbrain.valuation.provider import provider_health_snapshot
    from dealbrain.valuation.scale import category_readiness, current_scale_level
    try:
        providers = provider_health_snapshot()
        if not providers:
            from dealbrain.valuation.router import get_registry
            providers = get_registry().health()
    except Exception:
        providers = {}
    dry_run = bool(cfg.alert_dry_run)
    pc_raw = providers.get("pricecharting") or {}
    pc_status = str(pc_raw.get("status") or "NOT_CONFIGURED")
    if pc_status in {"NOT_CONFIGURED", "NEEDS_ACCESS", ""}:
        pc_display = {"status": "ON HOLD", "message": "Not required for First Profit Mode", **pc_raw}
    else:
        pc_display = {**pc_raw, "status": pc_status, "message": pc_raw.get("message") or "Optional / on hold"}
    try:
        from dealbrain.spend import spend_snapshot
        spend = spend_snapshot()
    except Exception:
        spend = {}
    first_profit_state = "PAUSED"
    if cfg.first_profit_live and int(cfg.scale_level or 0) >= 1:
        first_profit_state = "LIVE"
    elif cfg.first_profit_mode:
        first_profit_state = "READY"
    return {
        "operational": ebay_state,
        "message": ebay_message,
        "ebay_sniper_enabled": cfg.ebay_sniper_enabled,
        "ebay_scheduler_enabled": cfg.ebay_scheduler_enabled,
        "twilio_ok": twilio_configured(),
        "sms_enabled": cfg.sms_enabled and not dry_run and twilio_configured(),
        "alert_dry_run": dry_run,
        "scale_level": current_scale_level(),
        "providers": providers,
        "category_readiness": category_readiness(providers),
        "pricecharting": pc_display,
        "level1_retro": _level1_status(providers),
        "apify_ok": mp.apify_configured or mp.primary_provider == "mock",
        "marketplace_scheduler_enabled": mp.scheduler_enabled,
        "counts": counts,
        "last_ebay_run": last_ebay,
        "first_profit_mode": first_profit_state,
        "first_profit_live": bool(cfg.first_profit_live),
        "spend": spend,
        "apify_daily_cap_usd": cfg.apify_daily_cap_usd(),
    }


def radar_dealbrain_context(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    filters = filters or {}
    filters.setdefault("mode", "first_profit")
    filters.setdefault("sort", "best")
    status = dealbrain_status()
    try:
        mp_status = scanner_status()
    except Exception:
        mp_status = {"operational": "NOT CONFIGURED", "message": "Marketplace Scanner not configured"}
    deals = []
    try:
        deals = list_deal_feed(filters, limit=60)
    except Exception:
        deals = []
    from dealbrain.classify import class_emoji
    for deal in deals:
        deal["class_emoji"] = class_emoji(deal.get("classification") or "")
        if str(deal.get("source") or "").startswith("facebook"):
            deal["open_label"] = "OPEN FACEBOOK LISTING"
        elif str(deal.get("source") or "") == "ebay":
            deal["open_label"] = "OPEN EBAY LISTING"
        else:
            deal["open_label"] = "OPEN LISTING"
    counts = status.get("counts") or {}
    return {
        "mp_status": {
            "operational": mp_status.get("operational") or status.get("operational"),
            "message": mp_status.get("message") or status.get("message"),
        },
        "mp_message": "FIRST PROFIT — conservative active-market deals with enough spread that a wrong estimate can still make money.",
        "mp_apify_ok": status.get("apify_ok"),
        "mp_twilio_ok": status.get("twilio_ok"),
        "mp_counts": {
            "enabled_watches": 0,
            "new_listings": mp_status.get("new_listings") or 0,
            "hot": counts.get("hot") or 0,
            "buy": counts.get("strong") or 0,
            "monster": counts.get("monster") or 0,
            "strong": counts.get("strong") or 0,
            "last_scan": mp_status.get("last_success_at") and {"finished_at": mp_status.get("last_success_at")} or {},
            "next_scan_at": mp_status.get("next_scan") or "Scheduler off",
        },
        "mp_deals": deals,
        "mp_filters": filters,
        "mp_watches": [],
        "mp_default_location": "Atlantic City, New Jersey",
        "mp_scanner": mp_status,
        "facebook_level": mp_status.get("facebook_level") or (1 if status.get("scale_level") else 0),
        "fb_markets_active": mp_status.get("markets_active") or 0,
        "fb_precision_targets": mp_status.get("precision_targets") or 0,
        "fb_treasure_targets": mp_status.get("treasure_targets") or 0,
        "fb_runs_today": mp_status.get("runs_today") or 0,
        "fb_listings_seen_today": mp_status.get("listings_seen_today") or 0,
        "fb_unique_listings_today": mp_status.get("unique_listings_today") or 0,
        "fb_candidates_today": mp_status.get("candidates_today") or 0,
        "fb_discovery_health": mp_status.get("discovery_health") or mp_status.get("operational"),
        "fb_detail_health": mp_status.get("detail_health") or "IDLE",
        "fb_duplicate_rate": mp_status.get("duplicate_rate"),
        "db_status": status,
        "db_ebay_scheduler": status.get("ebay_scheduler_enabled"),
        "valuation_providers": status.get("providers") or {},
        "pricecharting": status.get("pricecharting") or {},
        "level1_retro": status.get("level1_retro") or {},
        "category_readiness": status.get("category_readiness") or {},
        "alert_dry_run": status.get("alert_dry_run"),
        "scale_level": status.get("scale_level", 0),
        "first_profit_mode": status.get("first_profit_mode") or "READY",
        "first_profit_spend": status.get("spend") or {},
        "apify_daily_cap_usd": status.get("apify_daily_cap_usd"),
    }
