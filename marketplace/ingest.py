from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from marketplace.config import MarketplaceConfig, get_config
from marketplace.models import ListingRef, ScanTarget
from marketplace.normalize import normalize_provider_item
from marketplace.stage1 import STAGE1_CANDIDATE, evaluate_stage1
from marketplace.store import (
    append_raw_event,
    apply_stage1,
    finish_run,
    get_run,
    get_target,
    listings_needing_detail,
    mark_details_fetched,
    record_target_failure,
    record_target_success,
    row_to_target,
    update_provider_health,
    upsert_listing,
)

logger = logging.getLogger("market_radar.marketplace")
_deep_analyzed = 0


def _maybe_analyze_candidate(listing: dict[str, Any], config: MarketplaceConfig | None = None, *, send_alerts: bool = True) -> dict[str, Any]:
    global _deep_analyzed
    try:
        from dealbrain.config import get_config as dealbrain_config
        from dealbrain.pipeline import analyze_and_store
        cfg = dealbrain_config()
        if _deep_analyzed >= max(0, cfg.deep_max_per_run):
            return {}
        previous_class = ""
        previous_price = listing.get("asking_price")
        try:
            from dealbrain.store import latest_verdict
            prior = latest_verdict(str(listing.get("id") or ""))
            previous_class = str(prior.get("classification") or "")
            previous_price = prior.get("asking_price") if prior.get("asking_price") is not None else listing.get("asking_price")
        except Exception:
            previous_class = ""
        verdict = analyze_and_store(
            listing,
            comps_lookup=None,
            send_alerts=send_alerts,
            previous_class=previous_class,
            previous_price=previous_price,
        )
        _deep_analyzed += 1
        return verdict or {}
    except Exception:
        logger.info("DEALBRAIN_ANALYZE_SKIPPED listing_id=%s", listing.get("id"))
        return {}


async def ingest_dataset(
    *,
    run_id: str,
    provider,
    dataset_id: str,
    apify_run_id: str = "",
    usage_usd: float | None = None,
    config: MarketplaceConfig | None = None,
) -> dict[str, Any]:
    cfg = config or get_config()
    run = get_run(run_id)
    if run.get("ingested"):
        logger.info("MARKETPLACE_INGEST_SKIPPED run_id=%s reason=already_ingested", run_id)
        return {"ok": True, "duplicate_ingest": True, "run_id": run_id}
    target_row = get_target(str(run.get("target_id") or ""))
    target = row_to_target(target_row) if target_row else ScanTarget(id=str(run.get("target_id") or ""), name="", query="")
    global _deep_analyzed
    _deep_analyzed = 0
    raw_count = 0
    unique_count = 0
    duplicate_count = 0
    candidate_count = 0
    malformed_count = 0
    missing_id = 0
    missing_price = 0
    class_counts = {"STRONG": 0, "HOT": 0, "MONSTER": 0}
    identity_verified = 0
    needs_verification = 0
    actionable = 0
    discord_alerts = 0
    new_ids: list[str] = []

    async for raw in provider.fetch_dataset(dataset_id):
        raw_count += 1
        append_raw_event(run_id, getattr(provider, "name", ""), dataset_id, str(raw.get("listingId") or raw.get("id") or ""), raw)
        listing = normalize_provider_item(
            raw,
            provider=getattr(provider, "name", ""),
            watch=target.to_dict(),
            run_id=apify_run_id or run_id,
            dataset_id=dataset_id,
        )
        if not listing:
            malformed_count += 1
            continue
        if listing.get("malformed") or not listing.get("source_listing_id"):
            missing_id += 1
            malformed_count += 1
            continue
        if listing.get("asking_price") is None and not listing.get("price_is_placeholder"):
            missing_price += 1
        saved, lifecycle, is_new = upsert_listing(listing, run_id, seen_duplicate_hours=cfg.seen_duplicate_hours)
        listing["lifecycle_status"] = lifecycle
        if is_new:
            unique_count += 1
            new_ids.append(str(saved.get("id") or ""))
        else:
            duplicate_count += 1
        stage = evaluate_stage1({**listing, **saved, "lifecycle_status": lifecycle}, target.to_dict())
        apply_stage1(str(saved.get("id") or ""), stage)
        try:
            from dealbrain.market_map import observation_from_listing
            from marketplace.store import save_price_observation
            obs = observation_from_listing({**listing, **saved, **stage})
            if obs:
                save_price_observation(obs)
        except Exception:
            pass
        if stage.get("stage1_status") == STAGE1_CANDIDATE:
            candidate_count += 1
        treasure = str(target.cadence_tier or "").upper() == "TREASURE" or str(target.query_type or "").upper() in {"BUNDLE", "GENERIC", "URGENCY"}
        if str(target.cadence_tier or "").upper() == "PRECISION":
            treasure = False
        unchanged = (not is_new) and str(lifecycle) not in {"PRICE_DROP", "RELISTED", "UPDATED"}
        should_analyze = False
        if not unchanged:
            if treasure:
                should_analyze = stage.get("stage1_status") == STAGE1_CANDIDATE
            elif stage.get("stage1_status") == STAGE1_CANDIDATE or str(lifecycle) == "PRICE_DROP":
                should_analyze = True
        if should_analyze:
            verdict = _maybe_analyze_candidate({**listing, **saved, "lifecycle_status": lifecycle}, config=cfg, send_alerts=True)
            klass = str((verdict or {}).get("classification") or "") if isinstance(verdict, dict) else str(verdict or "")
            if klass in class_counts:
                class_counts[klass] += 1
            if isinstance(verdict, dict) and verdict:
                from marketplace.identity import identity_is_exact
                from dealbrain.identity_gate import FEED_ACTIONABLE, FEED_NEEDS_VERIFICATION, needs_verification as _needs
                if identity_is_exact(str(verdict.get("identity_confidence") or "")):
                    identity_verified += 1
                if str(verdict.get("feed_lane") or "") == FEED_NEEDS_VERIFICATION or _needs(verdict):
                    needs_verification += 1
                if str(verdict.get("feed_lane") or "") == FEED_ACTIONABLE or klass in {"HOT", "MONSTER", "STRONG"}:
                    if identity_is_exact(str(verdict.get("identity_confidence") or "")):
                        actionable += 1
                if verdict.get("discord_sent") or verdict.get("alert_sent"):
                    discord_alerts += 1

    status = "completed_zero" if raw_count == 0 else "SUCCEEDED"
    try:
        from marketplace.ledger import persist_run_ledger, resolve_cost
        cost_usd, cost_kind = resolve_cost(usage_usd)
        if usage_usd in (None, "", 0, 0.0):
            usage_usd = cost_usd
        extra = {
            "deep_count": _deep_analyzed,
            "identity_verified_count": identity_verified,
            "needs_verification_count": needs_verification,
            "actionable_count": actionable,
            "discord_alert_count": discord_alerts,
            "cost_usd": cost_usd,
            "cost_kind": cost_kind,
            "success": True,
            "hot": class_counts["HOT"],
            "monster": class_counts["MONSTER"],
            "strong": class_counts["STRONG"],
        }
    except Exception:
        cost_usd, cost_kind, extra = float(usage_usd or 0), "actual" if usage_usd else "estimated", {}
    finish_run(
        run_id,
        status=status,
        dataset_id=dataset_id,
        apify_run_id=apify_run_id or run.get("apify_run_id") or "",
        raw_row_count=raw_count,
        unique_count=unique_count,
        candidate_count=candidate_count,
        duplicate_count=duplicate_count,
        malformed_count=malformed_count,
        usage_usd=usage_usd,
        ingested=1,
        error_code="" if raw_count else "zero_results",
        error_message="" if raw_count else "Scan completed — 0 listings",
        extra=extra,
    )
    try:
        persist_run_ledger(run_id, {
            "raw_row_count": raw_count,
            "unique_count": unique_count,
            "candidate_count": candidate_count,
            "duplicate_count": duplicate_count,
            "usage_usd": usage_usd,
            "status": status,
        })
    except Exception:
        pass
    try:
        from dealbrain.spend import record_apify_spend
        from dealbrain.store import record_query_stats
        if usage_usd:
            record_apify_spend(float(usage_usd))
        record_query_stats(
            "facebook_marketplace",
            f"{target.market_id}:{target.query}",
            target.cadence_tier or target.query_type or "",
            raw_rows=raw_count,
            unique_rows=unique_count,
            candidates=candidate_count,
            deep=_deep_analyzed,
            strong=class_counts["STRONG"],
            hot=class_counts["HOT"],
            monster=class_counts["MONSTER"],
            provider_cost=float(usage_usd or 0),
        )
    except Exception:
        pass
    next_due = (datetime.now(timezone.utc) + timedelta(seconds=target.cadence_seconds())).replace(microsecond=0).isoformat()
    record_target_success(target.id, next_due, unique_count=unique_count, candidate_count=candidate_count)
    denom = max(1, raw_count)
    update_provider_health(
        getattr(provider, "name", "unknown"),
        success=True,
        malformed_rate=malformed_count / denom,
        missing_id_rate=missing_id / denom,
        missing_price_rate=missing_price / denom,
        usage_usd=usage_usd,
    )
    logger.info(
        "MARKETPLACE_INGEST_COMPLETE run_id=%s raw=%s unique=%s candidates=%s duplicates=%s malformed=%s",
        run_id,
        raw_count,
        unique_count,
        candidate_count,
        duplicate_count,
        malformed_count,
    )
    if str(run.get("stage") or "discovery") == "discovery":
        skip_stage2 = False
        try:
            from dealbrain.config import get_config as dealbrain_config
            skip_stage2 = bool(getattr(dealbrain_config(), "first_profit_mode", True))
        except Exception:
            skip_stage2 = False
        if not skip_stage2 and candidate_count:
            await maybe_start_stage2(provider, config=cfg)
    return {
        "ok": True,
        "run_id": run_id,
        "raw_rows": raw_count,
        "unique_rows": unique_count,
        "candidates": candidate_count,
        "duplicates": duplicate_count,
        "malformed": malformed_count,
        "status": status,
        "usage_usd": usage_usd,
    }


async def maybe_start_stage2(provider, config: MarketplaceConfig | None = None) -> dict[str, Any]:
    cfg = config or get_config()
    if not cfg.scanner_enabled:
        return {"started": False, "reason": "scanner_disabled"}
    candidates = listings_needing_detail(limit=max(0, cfg.stage2_max_per_run))
    if not candidates:
        return {"started": False, "reason": "no_candidates"}
    refs = [
        ListingRef(
            source=str(row.get("source") or "facebook_marketplace"),
            source_listing_id=str(row.get("source_listing_id") or ""),
            canonical_url=str(row.get("canonical_url") or ""),
            title=str(row.get("title") or ""),
            provider=str(row.get("provider") or getattr(provider, "name", "")),
        )
        for row in candidates
        if row.get("canonical_url")
    ]
    if not refs:
        return {"started": False, "reason": "no_urls"}
    from marketplace.store import create_scan_run, mark_run_started

    local_run_id = create_scan_run({"id": "stage2"}, stage="detail", provider=getattr(provider, "name", ""), actor=getattr(provider, "actor", ""))
    started = await provider.start_detail_run(refs)
    if not started.ok:
        finish_run(local_run_id, status="FAILED", error_code="provider_error", error_message=started.error or "Marketplace provider error")
        return {"started": False, "reason": started.error or "provider_error"}
    mark_run_started(local_run_id, apify_run_id=started.run_id, dataset_id=started.dataset_id, actor=started.actor, status=started.status or "RUNNING")
    mark_details_fetched([str(row.get("id") or "") for row in candidates], local_run_id)
    logger.info("MARKETPLACE_STAGE2_STARTED run_id=%s listings=%s", local_run_id, len(refs))
    return {"started": True, "run_id": local_run_id, "apify_run_id": started.run_id, "count": len(refs)}


def mark_provider_failure(run_id: str, *, error_code: str, error_message: str, config: MarketplaceConfig | None = None) -> None:
    cfg = config or get_config()
    run = get_run(run_id)
    finish_run(run_id, status="FAILED", error_code=error_code, error_message=error_message, ingested=1)
    if run.get("target_id"):
        record_target_failure(str(run["target_id"]), breaker=cfg.circuit_breaker_failures, retry_seconds=cfg.circuit_retry_seconds)
    update_provider_health(str(run.get("provider") or "unknown"), success=False)
    logger.info("MARKETPLACE_RUN_FAILED run_id=%s code=%s", run_id, error_code)
