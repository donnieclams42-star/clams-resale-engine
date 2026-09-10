from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .alerts import format_digest, send_sms
from .config import apify_configured, settings, twilio_configured
from .pipeline import run_watch_scan
from .providers.apify import ApifyMarketplaceProvider
from .store import deal_feed, due_watches, init_db, latest_scan, mark_watch_scanned, recent_alerts

logger = logging.getLogger("market_radar.marketplace")

_thread: threading.Thread | None = None
_started = False
_running = False
_lock = threading.Lock()
_last_digest_at = 0.0


def runtime_status() -> dict[str, Any]:
    cfg = settings()
    scan = latest_scan() or {}
    error_code = str(scan.get("error_code") or "")
    scan_status = str(scan.get("status") or "")
    if not apify_configured():
        operational = "apify_not_configured"
    elif _running or scan_status == "running":
        operational = "scan_running"
    elif error_code:
        operational = error_code if error_code in {
            "actor_failed",
            "actor_timeout",
            "apify_request_failed",
            "dataset_unavailable",
            "apify_not_configured",
        } else "error"
    elif scan_status == "zero_results" or (scan_status == "completed" and int(scan.get("items_received") or 0) == 0):
        operational = "zero_results"
    elif scan_status in {"completed", "ok"}:
        operational = "completed"
    else:
        operational = "idle"
    return {
        "operational": operational,
        "apify_configured": apify_configured(),
        "twilio_configured": twilio_configured(),
        "running": bool(_running),
        "scheduler_enabled": bool(cfg.get("scheduler_enabled", False)),
        "last_scan": scan,
        "message": "",
    }


def _maybe_digest() -> None:
    global _last_digest_at
    cfg = settings()
    if not cfg.get("sms_digest_enabled") or not twilio_configured():
        return
    hours = int(cfg.get("sms_digest_hours") or 6)
    now = time.time()
    if _last_digest_at and now - _last_digest_at < hours * 3600:
        return
    deals = [row for row in deal_feed({"classification": ""}, limit=20) if str(row.get("classification") or "") in {"HOT", "BUY"}]
    recent = recent_alerts(hours=hours, channel="sms", sent_only=True)
    if not deals:
        return
    send_sms(format_digest(deals[:8]))
    _last_digest_at = now
    logger.info("MARKETPLACE_DIGEST_SENT deals=%s recent_alerts=%s", len(deals), len(recent))


def _loop() -> None:
    global _running
    while True:
        cfg = settings()
        interval = max(20, int(cfg.get("min_scan_minutes") or 20))
        try:
            if not apify_configured():
                logger.info("MARKETPLACE_SCAN_SKIPPED reason=apify_not_configured")
            else:
                due = due_watches(limit=int(cfg.get("max_watches_per_cycle") or 2))
                if due:
                    provider = ApifyMarketplaceProvider()
                    for watch in due[:2]:
                        _running = True
                        try:
                            run_watch_scan(watch, provider, enrich=False, send_alerts=True)
                            mark_watch_scanned(
                                watch.get("id"),
                                int(watch.get("scan_interval_minutes") or cfg.get("scan_interval_minutes") or 40),
                            )
                        except Exception as exc:
                            logger.info("MARKETPLACE_SCHEDULER_WATCH_ERROR error=%s", type(exc).__name__)
                        finally:
                            _running = False
                _maybe_digest()
        except Exception as exc:
            _running = False
            logger.info("MARKETPLACE_SCHEDULER_ERROR error=%s", type(exc).__name__)
        time.sleep(120 if not apify_configured() else max(60, interval))


def start_marketplace_scheduler() -> None:
    global _thread, _started
    init_db()
    cfg = settings()
    if not cfg.get("scheduler_enabled", False):
        logger.info("MARKETPLACE_SCHEDULER disabled")
        return
    with _lock:
        if _started and _thread and _thread.is_alive():
            return
        _started = True
        _thread = threading.Thread(target=_loop, daemon=True, name="marketplace-scanner")
        _thread.start()
        logger.info("MARKETPLACE_SCHEDULER started")
