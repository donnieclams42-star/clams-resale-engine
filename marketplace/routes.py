from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse

from marketplace.config import get_config
from marketplace.ingest import ingest_dataset, mark_provider_failure
from marketplace.models import TERMINAL_FAIL, TERMINAL_OK
from marketplace.planner import start_canary_runs
from marketplace.providers.factory import get_provider
from marketplace.store import get_run_by_apify_id, mark_run_started, mark_webhook_processed, remember_webhook
from marketplace.webhook_auth import event_id, token_from_request_values, verify_webhook_secret as _verify_secret
from marketplace.workers import acquire_canary_lock, release_canary_lock

logger = logging.getLogger("market_radar.marketplace")
router = APIRouter()
ADMIN_EMAILS = {"donnieclams42@gmail.com"}


def verify_webhook_secret(request: Request, secret: str) -> bool:
    token = token_from_request_values(
        str(request.query_params.get("token") or ""),
        str(request.headers.get("x-apify-webhook-secret") or ""),
        str(request.headers.get("authorization") or ""),
    )
    return _verify_secret(token, secret)


def _event_id(payload: dict[str, Any], event_type: str, run_id: str) -> str:
    return event_id(payload, event_type, run_id)


def _request_email(request: Request) -> str:
    return str(request.cookies.get("clams_user") or "").strip().lower()


async def _process_apify_event(payload: dict[str, Any], event_id: str) -> None:
    cfg = get_config()
    event_type = str(payload.get("eventType") or payload.get("event_type") or "")
    event_data = payload.get("eventData") or {}
    resource = payload.get("resource") or {}
    apify_run_id = str(event_data.get("actorRunId") or resource.get("id") or payload.get("runId") or "")
    dataset_id = str(resource.get("defaultDatasetId") or "")
    status = str(resource.get("status") or "")
    run = get_run_by_apify_id(apify_run_id) if apify_run_id else {}
    if not run:
        logger.info("MARKETPLACE_WEBHOOK_UNKNOWN_RUN apify_run_id=%s", apify_run_id)
        mark_webhook_processed(event_id)
        return
    local_id = str(run["id"])
    if event_type.endswith("SUCCEEDED") or status in TERMINAL_OK:
        provider = get_provider(str(run.get("provider") or cfg.primary_provider), cfg)
        if not dataset_id:
            polled = await provider.get_run(apify_run_id)
            dataset_id = polled.dataset_id
            status = polled.status or status
        mark_run_started(local_id, apify_run_id=apify_run_id, dataset_id=dataset_id, status="SUCCEEDED")
        await ingest_dataset(
            run_id=local_id,
            provider=provider,
            dataset_id=dataset_id,
            apify_run_id=apify_run_id,
            usage_usd=(resource.get("usageTotalUsd") if isinstance(resource, dict) else None),
            config=cfg,
        )
    elif any(event_type.endswith(part) for part in ("FAILED", "TIMED-OUT", "ABORTED", "TIMED_OUT")) or status in TERMINAL_FAIL:
        mark_provider_failure(local_id, error_code="provider_error", error_message="Marketplace provider error", config=cfg)
    mark_webhook_processed(event_id)


@router.post("/webhooks/apify")
async def apify_webhook(request: Request, background: BackgroundTasks):
    cfg = get_config()
    if not cfg.webhook_secret:
        return JSONResponse({"ok": False, "error": "not_configured", "message": "Marketplace Scanner not configured"}, status_code=503)
    if not verify_webhook_secret(request, cfg.webhook_secret):
        logger.info("MARKETPLACE_WEBHOOK_REJECTED reason=invalid_secret")
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    event_type = str(payload.get("eventType") or payload.get("event_type") or "")
    event_data = payload.get("eventData") or {}
    resource = payload.get("resource") or {}
    apify_run_id = str(event_data.get("actorRunId") or resource.get("id") or payload.get("runId") or "")
    event_id = _event_id(payload, event_type, apify_run_id)
    first = remember_webhook(event_id, event_type, apify_run_id, payload)
    if not first:
        return JSONResponse({"ok": True, "duplicate": True, "event_id": event_id})
    background.add_task(_process_apify_event, payload, event_id)
    logger.info("MARKETPLACE_WEBHOOK_ACCEPTED event=%s apify_run_id=%s", event_type, apify_run_id)
    return JSONResponse({"ok": True, "accepted": True, "event_id": event_id, "event_type": event_type})


@router.post("/api/radar/marketplace/canary")
async def marketplace_canary(request: Request, background: BackgroundTasks):
    email = _request_email(request)
    if not email:
        return JSONResponse({"ok": False, "error": "login_required"}, status_code=401)
    if email not in ADMIN_EMAILS:
        return JSONResponse({"ok": False, "error": "admin_required"}, status_code=403)
    cfg = get_config()
    if not cfg.apify_configured and cfg.primary_provider != "mock":
        return JSONResponse({"ok": False, "error": "not_configured", "message": "Marketplace Scanner not configured"}, status_code=400)
    if not cfg.scanner_enabled:
        return JSONResponse({"ok": False, "error": "paused", "message": "Marketplace Scanner paused"}, status_code=400)
    payload: dict[str, Any] = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    query = str(payload.get("query") or request.query_params.get("query") or "").strip()
    market_id = str(payload.get("market") or payload.get("market_id") or request.query_params.get("market") or "").strip()
    try:
        max_items = int(payload.get("max_items") or request.query_params.get("max_items") or 0)
    except Exception:
        max_items = 0
    try:
        stage2_max = int(payload.get("stage2_max") or request.query_params.get("stage2_max") or 0)
    except Exception:
        stage2_max = 0
    fallback_raw = payload.get("allow_fallback", request.query_params.get("allow_fallback"))
    allow_fallback = False
    if fallback_raw not in (None, ""):
        allow_fallback = str(fallback_raw).strip().lower() in {"1", "true", "yes", "on"}
    max_starts = 1 if query or market_id else 5
    if not acquire_canary_lock():
        return JSONResponse({"ok": False, "error": "run_locked", "message": "A Marketplace canary scan is already running"}, status_code=409)

    async def _run_locked():
        try:
            await start_canary_runs(
                cfg,
                query=query,
                market_id=market_id,
                max_items=max_items,
                max_starts=max_starts,
                stage2_max=stage2_max,
                allow_fallback=allow_fallback,
            )
        finally:
            release_canary_lock()

    background.add_task(_run_locked)
    return JSONResponse({
        "ok": True,
        "started": True,
        "message": "Marketplace canary scan started",
        "query": query,
        "market": market_id,
        "max_items": max_items,
        "stage2_max": stage2_max,
        "allow_fallback": allow_fallback,
        "sms": False,
    })
