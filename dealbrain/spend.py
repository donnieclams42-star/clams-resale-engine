from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from dealbrain.config import get_config
from marketplace.normalize import utc_now


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _kv_get(key: str, default: str = "0") -> str:
    try:
        from marketplace.store import connect
        with connect() as conn:
            row = conn.execute("SELECT value FROM marketplace_kv WHERE key = ?", (key,)).fetchone()
        if row:
            return str(row[0] if not hasattr(row, "keys") else row["value"] or default)
    except Exception:
        return default
    return default


def _kv_set(key: str, value: str) -> None:
    try:
        from marketplace.store import connect
        with connect() as conn:
            conn.execute(
                "INSERT INTO marketplace_kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
    except Exception:
        pass


def apify_spend_today() -> float:
    day = _today()
    sql_total = 0.0
    try:
        from marketplace.store import connect
        with connect() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(usage_usd), 0) FROM marketplace_scan_runs
                WHERE started_at LIKE ? AND COALESCE(stage, 'discovery') != 'detail'""",
                (f"{day}%",),
            ).fetchone()
        if row:
            sql_total = float(row[0] or 0)
    except Exception:
        sql_total = 0.0
    try:
        kv_total = float(_kv_get(f"apify_spend:{day}", "0") or 0)
    except Exception:
        kv_total = 0.0
    return max(sql_total, kv_total)


def record_apify_spend(amount: float) -> float:
    if not amount:
        return apify_spend_today()
    day = _today()
    current = apify_spend_today() + float(amount)
    _kv_set(f"apify_spend:{day}", f"{current:.4f}")
    return current


def ebay_calls_today() -> int:
    day = _today()
    try:
        return int(float(_kv_get(f"ebay_calls:{day}", "0") or 0))
    except Exception:
        return 0


def record_ebay_call(n: int = 1) -> int:
    day = _today()
    total = ebay_calls_today() + int(n)
    _kv_set(f"ebay_calls:{day}", str(total))
    return total


def unique_per_call_today() -> float:
    day = _today()
    calls = max(1, ebay_calls_today())
    try:
        unique = float(_kv_get(f"ebay_unique:{day}", "0") or 0)
    except Exception:
        unique = 0.0
    return round(unique / calls, 2)


def record_ebay_unique(n: int) -> None:
    day = _today()
    try:
        current = int(float(_kv_get(f"ebay_unique:{day}", "0") or 0))
    except Exception:
        current = 0
    _kv_set(f"ebay_unique:{day}", str(current + int(n)))


def ebay_scheduler_due(min_seconds: int = 1800) -> tuple[bool, str]:
    raw = _kv_get("ebay_scheduler_last_ts", "")
    if not raw:
        return True, "ok"
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        if elapsed < max(60, int(min_seconds)):
            return False, "interval"
    except Exception:
        return True, "ok"
    return True, "ok"


def mark_ebay_scheduler_run() -> None:
    _kv_set("ebay_scheduler_last_ts", datetime.now(timezone.utc).replace(microsecond=0).isoformat())


def can_spend_apify(estimated_usd: float = 0.05) -> tuple[bool, str, float]:
    cfg = get_config()
    cap = cfg.apify_daily_cap_usd()
    spent = apify_spend_today()
    if spent + float(estimated_usd or 0) > cap + 1e-9:
        return False, "apify_daily_cap", spent
    return True, "ok", spent


def can_call_ebay() -> tuple[bool, str, int]:
    cfg = get_config()
    used = ebay_calls_today()
    cap = int(cfg.level1_max_ebay_calls_per_day or 40)
    if used >= cap:
        return False, "ebay_daily_call_cap", used
    return True, "ok", used


def facebook_runs_today() -> int:
    day = _today()
    try:
        from marketplace.store import connect
        with connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM marketplace_scan_runs
                WHERE started_at LIKE ? AND COALESCE(stage, 'discovery') != 'detail'""",
                (f"{day}%",),
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def facebook_research_runs_today() -> int:
    day = _today()
    try:
        from marketplace.store import connect
        with connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM marketplace_scan_runs r
                JOIN marketplace_scan_targets t ON t.id = r.target_id
                WHERE r.started_at LIKE ?
                AND UPPER(COALESCE(t.cadence_tier, '')) = 'RESEARCH'
                AND COALESCE(r.stage, 'discovery') != 'detail'""",
                (f"{day}%",),
            ).fetchone()
        return int(row[0] or 0) if row else 0
    except Exception:
        return 0


def leftover_research_gate(
    *,
    runs_today: int,
    research_runs_today: int,
    remaining_usd: float,
    usd_per_run: float = 0.016,
    local_allotment: int = 30,
    max_research_runs: int = 1,
) -> tuple[bool, str]:
    """Remote research only after local hunting used its allotment, and only with leftover dollars.

    Boosted budget must not become extra remote research. Cap leftover research at the
    base-cap leftover (usually 1 run), not at the boosted remainder.
    """
    if int(runs_today or 0) < int(local_allotment or 30):
        return False, "local_allotment_reserved"
    per = float(usd_per_run or 0.016)
    if per <= 0 or float(remaining_usd or 0) < per:
        return False, "no_leftover_budget"
    allowed = max(0, int(max_research_runs or 0))
    if allowed <= 0:
        return False, "no_leftover_budget"
    if int(research_runs_today or 0) >= allowed:
        return False, "leftover_research_cap"
    return True, "ok"


def can_start_facebook_run(estimated_usd: float = 0.02, *, leftover_research: bool = False) -> tuple[bool, str, dict[str, Any]]:
    cfg = get_config()
    spent = apify_spend_today()
    cap = cfg.apify_daily_cap_usd()
    runs = facebook_runs_today()
    run_cap = int(cfg.level1_max_fb_runs_per_day or 30)
    ok_spend, reason, _spent = can_spend_apify(estimated_usd)
    try:
        from dealbrain.budget import current_tier_name, effective_run_cap, boost_targeting
        run_cap = effective_run_cap(run_cap)
        meta = {"spent": spent, "cap": cap, "runs": runs, "run_cap": run_cap, "budget_tier": current_tier_name(), "boost": boost_targeting()}
    except Exception:
        meta = {"spent": spent, "cap": cap, "runs": runs, "run_cap": run_cap}
    remaining = cap - spent
    meta["remaining"] = round(remaining, 4)
    meta["protect_core_regions"] = remaining < max(0.12, estimated_usd * 7)
    if leftover_research:
        meta["leftover_research"] = True
        meta["protect_core_regions"] = False
        if not ok_spend:
            return False, reason, meta
        try:
            from marketplace.catalog import LEVEL1_MAX_RUNS_PER_DAY, estimate_phase2_remote_cost
            local_allotment = int(LEVEL1_MAX_RUNS_PER_DAY or 30)
            max_research = int((estimate_phase2_remote_cost() or {}).get("leftover_runs") or 0)
        except Exception:
            local_allotment = int(cfg.level1_max_fb_runs_per_day or 30)
            max_research = 1
        ok_left, left_reason = leftover_research_gate(
            runs_today=runs,
            research_runs_today=facebook_research_runs_today(),
            remaining_usd=remaining,
            usd_per_run=float(estimated_usd or 0.016),
            local_allotment=local_allotment,
            max_research_runs=max_research,
        )
        if not ok_left:
            return False, left_reason, meta
        return True, "ok", meta
    if not ok_spend:
        return False, reason, meta
    if runs >= run_cap:
        return False, "facebook_daily_run_cap", meta
    raw = _kv_get("fb_level1_last_start_ts", "")
    if raw:
        try:
            last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            from marketplace.catalog import MARKET_STAGGER_MINUTES
            if (datetime.now(timezone.utc) - last).total_seconds() < MARKET_STAGGER_MINUTES * 60:
                return False, "market_stagger", meta
        except Exception:
            pass
    return True, "ok", meta


def facebook_cap_state(estimated_usd: float = 0.016) -> tuple[str, str, dict[str, Any]]:
    ok, reason, meta = can_start_facebook_run(estimated_usd)
    from marketplace.ledger import cap_state_from_meta
    return cap_state_from_meta(meta, ok=ok, reason=reason), reason, meta


def mark_facebook_level1_start(market_id: str = "") -> None:
    _kv_set("fb_level1_last_start_ts", datetime.now(timezone.utc).replace(microsecond=0).isoformat())
    _kv_set("fb_level1_last_market", str(market_id or ""))


def last_facebook_market() -> str:
    return _kv_get("fb_level1_last_market", "")


def spend_snapshot() -> dict[str, Any]:
    cfg = get_config()
    snap = {
        "apify_spend_today": round(apify_spend_today(), 4),
        "apify_daily_cap_usd": cfg.apify_daily_cap_usd(),
        "ebay_calls_today": ebay_calls_today(),
        "ebay_call_cap": cfg.level1_max_ebay_calls_per_day,
        "facebook_runs_today": facebook_runs_today(),
        "facebook_run_cap": cfg.level1_max_fb_runs_per_day,
        "unique_per_call": unique_per_call_today(),
        "as_of": utc_now(),
    }
    try:
        from dealbrain.budget import budget_snapshot, effective_run_cap
        snap.update(budget_snapshot())
        snap["facebook_run_cap"] = effective_run_cap(int(cfg.level1_max_fb_runs_per_day or 30))
    except Exception:
        pass
    return snap
