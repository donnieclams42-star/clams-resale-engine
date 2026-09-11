from __future__ import annotations

from typing import Any

from marketplace.catalog import (
    ESTIMATED_APIFY_USD_PER_RUN,
    ESTIMATED_DAILY_APIFY_USD,
    MARKET_STAGGER_MINUTES,
    PRECISION_CADENCE_MINUTES,
    PRECISION_RESULT_LIMIT,
    TREASURE_CADENCE_HOURS,
    TREASURE_RESULT_LIMIT,
    first_profit_level1_markets,
)
from marketplace.config import get_config
from marketplace.store import get_provider_health, scanner_counts
from marketplace.workers import runtime_flags


def facebook_query_recommendations(min_runs: int = 3) -> list[dict[str, Any]]:
    try:
        from dealbrain.store import list_query_stats
        rows = list_query_stats("facebook_marketplace", limit=80)
    except Exception:
        return []
    recs: list[dict[str, Any]] = []
    for row in rows:
        runs = int(row.get("runs") or 0)
        if runs < min_runs:
            continue
        raw = int(row.get("raw_rows") or 0)
        unique = int(row.get("unique_rows") or 0)
        candidates = int(row.get("candidates") or 0)
        useful = int(row.get("strong") or 0) + int(row.get("hot") or 0) + int(row.get("monster") or 0)
        dup_rate = round(1 - (unique / raw), 3) if raw else 0.0
        reasons = []
        if raw and dup_rate >= 0.8:
            reasons.append("high_duplicates")
        if candidates == 0:
            reasons.append("zero_candidates")
        if useful == 0 and candidates == 0:
            reasons.append("zero_useful_inventory")
        if not reasons:
            continue
        recs.append({
            "query": row.get("query") or "",
            "runs": runs,
            "duplicate_rate": dup_rate,
            "candidates": candidates,
            "reason": ",".join(reasons),
            "recommendation": "slow this target; do not increase spend",
        })
    return recs


def _run_health(run: dict[str, Any], *, waiting_message: str) -> tuple[str, str]:
    status = str((run or {}).get("status") or "")
    if not run:
        return "IDLE", waiting_message
    if status in {"FAILED", "provider_error"}:
        err = str(run.get("error_message") or run.get("error_code") or "Marketplace provider error")
        if run.get("error_code") == "zero_results":
            return "LIVE", "Scan completed — 0 listings"
        return "DEGRADED", err
    if status in {"SUCCEEDED", "completed", "completed_zero"}:
        if status == "completed_zero" or run.get("error_code") == "zero_results":
            return "LIVE", "Scan completed — 0 listings"
        return "LIVE", "Marketplace scanner is live"
    if status in {"PENDING", "RUNNING", "READY", "CREATED"}:
        return "LIVE", "Scan in progress"
    return "LIVE", waiting_message


def scanner_status() -> dict[str, Any]:
    cfg = get_config()
    try:
        counts = scanner_counts()
    except Exception:
        counts = {}
    last = counts.get("last_discovery") or counts.get("last_run") or {}
    last_ok = counts.get("last_success") or {}
    last_detail = counts.get("last_detail") or {}
    flags = runtime_flags()
    discovery_state, discovery_message = _run_health(last, waiting_message="Marketplace scanner is waiting for the first successful scan")
    detail_state, detail_message = _run_health(last_detail, waiting_message="Detail fetch idle")
    if not last_detail:
        detail_state, detail_message = "IDLE", "Detail fetch not required for First Profit discovery"
    if not cfg.apify_configured and cfg.primary_provider != "mock":
        operational = "NOT CONFIGURED"
        message = "Marketplace Scanner not configured"
        discovery_state = "NOT CONFIGURED"
    elif not cfg.scanner_enabled:
        operational = "PAUSED"
        message = "Marketplace Scanner paused"
        discovery_state = "PAUSED"
    else:
        operational = discovery_state if discovery_state in {"LIVE", "DEGRADED", "IDLE"} else "LIVE"
        if operational == "IDLE":
            operational = "LIVE"
            message = discovery_message
        else:
            message = discovery_message
        if last_ok and operational == "LIVE":
            message = "Marketplace discovery is live"

    payload = {
        "operational": operational,
        "message": message,
        "discovery_health": discovery_state if discovery_state != "IDLE" else "LIVE",
        "discovery_message": discovery_message,
        "detail_health": detail_state,
        "detail_message": detail_message,
        "facebook_level": 1 if cfg.scheduler_enabled else 0,
        "markets_active": int(counts.get("enabled_markets") or 0),
        "precision_targets": int(counts.get("precision_targets") or 0),
        "treasure_targets": int(counts.get("treasure_targets") or 0),
        "runs_today": int(counts.get("runs_today") or 0),
        "listings_seen_today": int(counts.get("seen_today") or 0),
        "unique_listings_today": int(counts.get("unique_today") or 0),
        "candidates_today": int(counts.get("candidates_today") or counts.get("candidates") or 0),
        "raw_today": int(counts.get("raw_today") or 0),
        "unique_run_today": int(counts.get("unique_run_today") or 0),
        "duplicate_today": int(counts.get("duplicate_today") or 0),
        "precision_cadence_minutes": PRECISION_CADENCE_MINUTES,
        "treasure_cadence_hours": TREASURE_CADENCE_HOURS,
        "precision_result_cap": PRECISION_RESULT_LIMIT,
        "treasure_result_cap": TREASURE_RESULT_LIMIT,
        "stagger_minutes": MARKET_STAGGER_MINUTES,
        "estimated_usd_per_run": ESTIMATED_APIFY_USD_PER_RUN,
        "estimated_daily_apify_usd": ESTIMATED_DAILY_APIFY_USD,
        "slowdown_recommendations": facebook_query_recommendations(),
        "active_market_cells": [row["id"] for row in first_profit_level1_markets()],
        "primary_provider": cfg.primary_provider,
        "actor": cfg.actor_for(cfg.primary_provider),
        "configured": cfg.apify_configured or cfg.primary_provider == "mock",
        "scanner_enabled": cfg.scanner_enabled,
        "scheduler_enabled": cfg.scheduler_enabled,
        "last_success_at": (last_ok or {}).get("finished_at") or (last_ok or {}).get("started_at") or "",
        "last_scan_result_count": int((last_ok or last or {}).get("raw_row_count") or 0),
        "new_listings": int(counts.get("new_count") or 0),
        "stage1_candidates": int(counts.get("candidates") or 0),
        "running_scans": int(counts.get("running") or 0),
        "failed_targets": int(counts.get("failed_targets") or 0),
        "next_scan": counts.get("next_due_at") or "",
        "listings_24h": int(counts.get("listings_24h") or 0),
        "last_error": str(last.get("error_message") or ""),
        "last_status": str(last.get("status") or ""),
        "last_detail_status": str(last_detail.get("status") or ""),
        "worker_error": flags.get("last_error") or "",
        "provider_health": {},
    }
    raw = int(payload.get("raw_today") or 0)
    dups = int(payload.get("duplicate_today") or 0)
    payload["duplicate_rate"] = round(dups / raw, 3) if raw else None
    try:
        payload["provider_health"] = get_provider_health(cfg.primary_provider) or {}
    except Exception:
        pass
    return payload


def radar_marketplace_context(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    from marketplace.store import list_feed, list_targets

    status = scanner_status()
    deals = []
    try:
        deals = list_feed(filters or {}, limit=40)
    except Exception:
        deals = []
    for deal in deals:
        deal["facebook_url"] = deal.get("canonical_url") or ""
        reasons = deal.get("stage1_reasons") or []
        if isinstance(reasons, str):
            deal["stage1_reasons"] = [reasons]
    payload = {
        "mp_status": status,
        "mp_deals": deals,
        "mp_filters": filters or {},
        "mp_canary_targets": [],
    }
    try:
        payload["mp_canary_targets"] = list_targets(canary_only=True)
    except Exception:
        pass
    return payload
