from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

from marketplace.config import get_config
from marketplace.planner import planner_tick
from marketplace.recovery import recover_stale_runs
from marketplace.store import init_store, seed_defaults, disable_all_scan_targets, enable_first_profit_level1_targets

logger = logging.getLogger("market_radar.marketplace")

_thread: Optional[threading.Thread] = None
_started = False
_lock = threading.Lock()
_runtime = {"enabled": True, "running": False, "last_error": "", "canary_lock": False}


def start_marketplace_workers(cache_dir: str) -> None:
    global _thread, _started
    cfg = get_config()
    init_store(cache_dir)
    try:
        from marketplace.ledger import backfill_run_ledger_from_scan_runs
        backfill_run_ledger_from_scan_runs()
    except Exception:
        logger.info("RUN_LEDGER_BACKFILL_SKIPPED")
    seed_defaults(cfg.primary_provider if cfg.primary_provider != "mock" else "rigelbytes")
    if cfg.scheduler_enabled:
        try:
            from dealbrain.config import get_config as dealbrain_config
            live = bool(getattr(dealbrain_config(), "first_profit_live", False))
        except Exception:
            live = True
        if live:
            summary = enable_first_profit_level1_targets(cfg.primary_provider if cfg.primary_provider != "mock" else "rigelbytes")
            logger.info(
                "MARKETPLACE_LEVEL1_TARGETS_ENABLED markets=%s precision=%s treasure=%s",
                summary.get("markets"),
                summary.get("precision_targets"),
                summary.get("treasure_targets"),
            )
            try:
                from marketplace.store import enable_phase2_expansion
                from marketplace.catalog import estimate_phase2_remote_cost
                remote_cost = estimate_phase2_remote_cost()
                enable_remote = int(remote_cost.get("leftover_runs") or 0) >= 1
                phase2 = enable_phase2_expansion(
                    cfg.primary_provider if cfg.primary_provider != "mock" else "rigelbytes",
                    enable_repair=True,
                    enable_generic=True,
                    enable_remote=enable_remote,
                )
                logger.info(
                    "FACEBOOK_PHASE2_ENABLED repair=%s generic=%s remote=%s leftover_usd=%s",
                    phase2.get("repair_targets"),
                    phase2.get("generic_targets"),
                    phase2.get("remote_enabled"),
                    (phase2.get("remote_cost") or {}).get("leftover_usd"),
                )
            except Exception:
                logger.info("FACEBOOK_PHASE2_SEED_SKIPPED")
            try:
                from dealbrain.pipeline import recheck_actionable_inventory
                from marketplace.ledger import save_identity_recheck
                report = recheck_actionable_inventory(send_alerts=False)
                save_identity_recheck(report)
                logger.info("IDENTITY_RECHECK %s", report)
            except Exception:
                logger.info("IDENTITY_RECHECK_SKIPPED")
        else:
            forced_off = disable_all_scan_targets()
            if forced_off:
                logger.info("MARKETPLACE_TARGETS_FORCED_OFF count=%s", forced_off)
    else:
        forced_off = disable_all_scan_targets()
        if forced_off:
            logger.info("MARKETPLACE_TARGETS_FORCED_OFF count=%s", forced_off)
    with _lock:
        if _started and _thread and _thread.is_alive():
            return
        _started = True
        _runtime["enabled"] = cfg.scanner_enabled
        _thread = threading.Thread(target=_loop, daemon=True, name="market-radar-marketplace")
        _thread.start()
    logger.info(
        "MARKETPLACE_WORKERS_STARTED configured=%s scanner=%s scheduler=%s provider=%s",
        cfg.apify_configured,
        cfg.scanner_enabled,
        cfg.scheduler_enabled,
        cfg.primary_provider,
    )


def runtime_flags() -> dict:
    return dict(_runtime)


def acquire_canary_lock() -> bool:
    with _lock:
        if _runtime.get("canary_lock"):
            return False
        _runtime["canary_lock"] = True
        return True


def release_canary_lock() -> None:
    with _lock:
        _runtime["canary_lock"] = False


def _loop() -> None:
    while True:
        cfg = get_config()
        _runtime["enabled"] = cfg.scanner_enabled
        try:
            _runtime["running"] = True
            asyncio.run(_tick(cfg))
            _runtime["last_error"] = ""
        except Exception as exc:
            _runtime["last_error"] = str(exc)
            logger.info("MARKETPLACE_WORKER_ERROR error=%s", type(exc).__name__)
        finally:
            _runtime["running"] = False
        time.sleep(max(15, min(cfg.planner_interval_seconds, cfg.recovery_interval_seconds)))


async def _tick(cfg) -> None:
    from marketplace.recovery import recover_stale_runs
    await recover_stale_runs(cfg)
    await planner_tick(cfg)
    try:
        from marketplace.planner import planner_research_tick
        await planner_research_tick(cfg)
    except Exception:
        logger.info("MARKET_RESEARCH_TICK_SKIPPED")
    try:
        from dealbrain.valuation.pricecharting.refresh import refresh_tick
        refresh_tick()
    except Exception:
        logger.info("PRICECHARTING_REFRESH_SKIPPED")
    try:
        from dealbrain.ebay_sniper import scheduler_tick
        await scheduler_tick()
    except Exception:
        logger.info("EBAY_SNIPER_TICK_SKIPPED")
