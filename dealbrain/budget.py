"""Profit-funded Facebook budget ladder.

BASE $0.50/day. A verified $100+ opportunity can temporarily boost to $1.00
for 48 hours. A recorded SOLD flip with net profit >= $100 unlocks $2.00/day.
Nothing above $2.00 without Donald's explicit approval.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from marketplace.normalize import utc_now

BASE_CAP_USD = 0.50
BOOST_CAP_USD = 1.00
UNLOCK_CAP_USD = 2.00
ABSOLUTE_AUTO_MAX_USD = 2.00
BOOST_HOURS = 48
MIN_VERIFIED_PROFIT = 100.0
MIN_REALIZED_PROFIT = 100.0

KV_BOOST_UNTIL = "fb_budget_boost_until"
KV_BOOST_FAMILY = "fb_budget_boost_family"
KV_BOOST_QUERY_TYPE = "fb_budget_boost_query_type"
KV_BOOST_QUERY = "fb_budget_boost_query"
KV_BOOST_MARKET = "fb_budget_boost_market"
KV_BOOST_LISTING = "fb_budget_boost_listing_id"
KV_UNLOCK = "fb_realized_unlock"
KV_UNLOCK_AT = "fb_realized_unlock_at"
KV_PROJECTED_PREFIX = "fb_projected_profit:"

STRONG_IDENTITY = {"CONFIRMED", "STRONG", "EXACT_CONFIRMED", "EXACT_STRONG"}
WEAK_IDENTITY = {"NONE", "LOW", "FAMILY_ONLY", "AMBIGUOUS", "CONTRADICTORY", "ACCESSORY_ONLY", "PARTS_ONLY", "BOX_ONLY", "BUNDLE_UNRESOLVED", "FALSE_MATCH", "UNKNOWN", ""}
INVALID_CLASSES = {"PASS", "WATCH", ""}
INVALID_RISK = {"HIGH"}


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _kv_get(key: str, default: str = "") -> str:
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


def _f(value: Any) -> float:
    try:
        if value in (None, "", "UNKNOWN"):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _parse_iso(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def realized_unlock_active() -> bool:
    return str(_kv_get(KV_UNLOCK, "0") or "0") in {"1", "true", "TRUE", "yes"}


def boost_until() -> datetime | None:
    return _parse_iso(_kv_get(KV_BOOST_UNTIL, ""))


def boost_active(now: datetime | None = None) -> bool:
    if realized_unlock_active():
        return False
    until = boost_until()
    if until is None:
        return False
    stamp = now or datetime.now(timezone.utc)
    return stamp < until


def boost_targeting() -> dict[str, Any]:
    active = boost_active()
    return {
        "active": active,
        "until": _kv_get(KV_BOOST_UNTIL, ""),
        "family": _kv_get(KV_BOOST_FAMILY, ""),
        "query_type": _kv_get(KV_BOOST_QUERY_TYPE, ""),
        "query": _kv_get(KV_BOOST_QUERY, ""),
        "market": _kv_get(KV_BOOST_MARKET, ""),
        "listing_id": _kv_get(KV_BOOST_LISTING, ""),
    }


def current_tier_cap() -> float:
    if realized_unlock_active():
        return UNLOCK_CAP_USD
    if boost_active():
        return BOOST_CAP_USD
    return BASE_CAP_USD


def current_tier_name() -> str:
    if realized_unlock_active():
        return "UNLOCK_2.00"
    if boost_active():
        return "BOOST_1.00"
    return "BASE_0.50"


def effective_facebook_cap(base: float, provider_max: float = 3.0) -> float:
    ladder = current_tier_cap()
    if ladder > BASE_CAP_USD + 1e-9:
        return min(float(provider_max or 3.0), ABSOLUTE_AUTO_MAX_USD, ladder)
    return min(float(provider_max or 3.0), ABSOLUTE_AUTO_MAX_USD, float(base or BASE_CAP_USD))


def effective_run_cap(base_runs: int = 30) -> int:
    base = max(1, int(base_runs or 30))
    if realized_unlock_active():
        return min(base + 30, 60)
    if boost_active():
        return min(base + 15, 45)
    return base


def infer_boost_target(listing: dict[str, Any] | None, valuation: dict[str, Any] | None = None) -> dict[str, str]:
    listing = listing or {}
    valuation = valuation or {}
    title = f"{listing.get('title') or ''} {valuation.get('title') or ''}".lower()
    family = str(valuation.get("candidate_product_family") or listing.get("candidate_product_family") or "")
    query = str(listing.get("query") or valuation.get("query") or "")
    market = str(valuation.get("metro_id") or listing.get("market_id") or listing.get("metro_id") or "")
    query_type = "PRECISION"
    tags = valuation.get("opportunity_types") or listing.get("opportunity_types") or []
    tags_u = {str(t).upper() for t in tags}
    if valuation.get("repair_alert_ok") or "REPAIR_ARBITRAGE" in tags_u or "cracked" in title or "broken" in title or "repair" in title:
        query_type = "REPAIR"
    elif "lot" in title or "bundle" in title or "nintendo" in title or "console" in family or family in {"retro-nintendo", "ps5", "switch-oled"}:
        query_type = "TREASURE"
    elif "MARKET_ARBITRAGE" in tags_u and market:
        query_type = "RESEARCH"
    if "iphone" in family or "iphone" in title:
        family = family or "iphone-15-pro"
        if query_type == "REPAIR":
            query = query or "cracked iphone"
    if "switch" in family or "nintendo" in title:
        family = family or "switch-oled"
        if query_type == "TREASURE":
            query = query or "nintendo lot"
    return {
        "family": family,
        "query_type": query_type,
        "query": query,
        "market": market,
    }


def qualifies_for_budget_boost(listing: dict[str, Any] | None, valuation: dict[str, Any] | None = None) -> tuple[bool, str]:
    listing = listing or {}
    valuation = valuation or {}
    klass = str(valuation.get("classification") or listing.get("classification") or "").upper()
    ident = str(valuation.get("identity_confidence") or listing.get("identity_confidence") or "").upper()
    risk = str(valuation.get("risk") or listing.get("risk") or "").upper()
    family = str(valuation.get("candidate_product_family") or listing.get("candidate_product_family") or "").lower()
    profit = max(
        _f(valuation.get("repair_expected_profit")),
        _f(valuation.get("expected_profit")),
        _f(valuation.get("cross_market_expected_profit")),
    )
    if klass in INVALID_CLASSES:
        return False, "class_not_verified"
    if klass == "RISK" and not valuation.get("repair_alert_ok"):
        return False, "risk_not_verified"
    if risk in INVALID_RISK and not valuation.get("repair_alert_ok"):
        return False, "risk_high"
    if ident in WEAK_IDENTITY or ident not in STRONG_IDENTITY:
        return False, "identity_not_strong"
    if valuation.get("identity_contradiction") or ident == "CONTRADICTORY":
        return False, "identity_conflicted"
    if valuation.get("accessory_mismatch") or str(valuation.get("item_kind") or listing.get("item_kind") or "").lower() == "accessory":
        return False, "accessory"
    if valuation.get("extreme_anomaly") and ident not in STRONG_IDENTITY:
        return False, "extreme_anomaly_unresolved_identity"
    if "switch" in family and ident not in {"CONFIRMED", "EXACT_CONFIRMED"}:
        return False, "title_only_variant"
    if str(valuation.get("deal_lane") or "") == "MARKET_RESEARCH" and str(valuation.get("acquisition_type") or "") == "LOCAL_PICKUP":
        return False, "remote_pickup_not_actionable"
    repair_type = str(valuation.get("repair_type") or "")
    if repair_type and repair_type not in {"", "UNKNOWN"} and not valuation.get("repair_alert_ok"):
        return False, "repair_not_verified"
    if valuation.get("cost_status") == "UNKNOWN" or valuation.get("cost_known") is False:
        return False, "repair_cost_unknown"
    if profit < MIN_VERIFIED_PROFIT:
        return False, "profit_below_100"
    if klass in {"HOT", "MONSTER", "STRONG"} or valuation.get("repair_alert_ok"):
        return True, "ok"
    return False, "class_not_verified"


def maybe_apply_opportunity_boost(listing: dict[str, Any] | None, valuation: dict[str, Any] | None = None) -> dict[str, Any]:
    ok, reason = qualifies_for_budget_boost(listing, valuation)
    record_projected_profit(valuation or {})
    if not ok:
        return {"applied": False, "reason": reason, "tier": current_tier_name()}
    target = infer_boost_target(listing, valuation)
    _kv_set(KV_BOOST_FAMILY, target.get("family") or "")
    _kv_set(KV_BOOST_QUERY_TYPE, target.get("query_type") or "")
    _kv_set(KV_BOOST_QUERY, target.get("query") or "")
    _kv_set(KV_BOOST_MARKET, target.get("market") or "")
    _kv_set(KV_BOOST_LISTING, str((listing or {}).get("id") or (valuation or {}).get("listing_id") or ""))
    if realized_unlock_active():
        return {"applied": False, "reason": "already_unlocked_2", "tier": current_tier_name(), "targeting": target}
    if not boost_active():
        until = datetime.now(timezone.utc) + timedelta(hours=BOOST_HOURS)
        _kv_set(KV_BOOST_UNTIL, until.replace(microsecond=0).isoformat())
    return {"applied": True, "reason": "ok", "tier": current_tier_name(), "targeting": target, "until": _kv_get(KV_BOOST_UNTIL, "")}


def maybe_unlock_realized_tier(*, profit: Any = None, sold: bool = False) -> dict[str, Any]:
    if not sold:
        return {"unlocked": False, "reason": "not_sold"}
    if _f(profit) < MIN_REALIZED_PROFIT:
        return {"unlocked": False, "reason": "realized_profit_below_100"}
    _kv_set(KV_UNLOCK, "1")
    _kv_set(KV_UNLOCK_AT, utc_now())
    return {"unlocked": True, "reason": "ok", "tier": current_tier_name()}


def record_projected_profit(valuation: dict[str, Any] | None) -> float:
    valuation = valuation or {}
    klass = str(valuation.get("classification") or "").upper()
    profit = 0.0
    if valuation.get("repair_alert_ok"):
        profit = max(_f(valuation.get("repair_expected_profit")), _f(valuation.get("expected_profit")))
    elif klass in {"HOT", "MONSTER", "STRONG"}:
        profit = max(_f(valuation.get("expected_profit")), _f(valuation.get("cross_market_expected_profit")))
    if profit <= 0:
        return projected_profit_today()
    day = _today()
    total = projected_profit_today() + profit
    _kv_set(f"{KV_PROJECTED_PREFIX}{day}", f"{total:.2f}")
    return total


def projected_profit_today() -> float:
    try:
        return float(_kv_get(f"{KV_PROJECTED_PREFIX}{_today()}", "0") or 0)
    except Exception:
        return 0.0


def realized_profit_total() -> float:
    try:
        from marketplace.store import connect
        with connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(profit), 0) FROM valuation_own_sales WHERE sale_price IS NOT NULL AND sale_price != ''"
            ).fetchone()
        return float(row[0] or 0) if row else 0.0
    except Exception:
        return 0.0


def facebook_run_priority_lanes(*, protect_core: bool = False, runs_today: int = 0, extra_budget: bool = False) -> list[str]:
    """When the cap is tight, money-hunting comes first. Extra budget follows the winning pattern."""
    if extra_budget:
        lanes = ["BOOST", "CORE_PRECISION", "CORE_REPAIR"]
        if not protect_core:
            lanes.extend(["NORTH_PRECISION", "LOCAL_TREASURE"])
        return lanes
    if protect_core:
        return ["CORE_PRECISION", "CORE_REPAIR"]
    slot = int(runs_today or 0) % 6
    primary = {
        0: "CORE_PRECISION",
        1: "CORE_PRECISION",
        2: "CORE_PRECISION",
        3: "CORE_REPAIR",
        4: "NORTH_PRECISION",
        5: "LOCAL_TREASURE",
    }.get(slot, "CORE_PRECISION")
    order = [primary]
    for lane in ("CORE_PRECISION", "CORE_REPAIR", "NORTH_PRECISION", "LOCAL_TREASURE"):
        if lane not in order:
            order.append(lane)
    return order


def estimate_remote_research_cost(*, usd_per_run: float = 0.016, cadence_hours: int = 36, metros: int = 6, queries: int = 8, daily_cap: float = 0.50, local_runs: int = 30) -> dict[str, Any]:
    unconstrained_runs = (metros * queries) * (24.0 / max(24, int(cadence_hours or 36)))
    unconstrained_usd = round(unconstrained_runs * usd_per_run, 4)
    local_usd = round(local_runs * usd_per_run, 4)
    leftover = round(max(0.0, daily_cap - local_usd), 4)
    leftover_runs = int(leftover // usd_per_run) if usd_per_run else 0
    fits = unconstrained_usd <= leftover + 1e-9
    return {
        "metros": metros,
        "queries": queries,
        "cadence_hours": cadence_hours,
        "unconstrained_daily_runs": round(unconstrained_runs, 2),
        "unconstrained_daily_usd": unconstrained_usd,
        "local_daily_usd": local_usd,
        "leftover_usd": leftover,
        "leftover_runs": leftover_runs,
        "fits_in_leftover": fits,
        "enable_mode": "leftover_only",
        "note": "Do not raise the $0.50 cap for research. Remote runs only if leftover remains after local hunting.",
    }


def budget_snapshot() -> dict[str, Any]:
    try:
        from dealbrain.spend import apify_spend_today
        spend = float(apify_spend_today() or 0)
    except Exception:
        spend = 0.0
    projected = projected_profit_today()
    realized = realized_profit_total()
    projected_per = round(projected / spend, 2) if spend >= 0.05 else None
    realized_per = round(realized / spend, 2) if spend >= 0.05 and realized else None
    targeting = boost_targeting()
    return {
        "facebook_spend_today": round(spend, 4),
        "projected_profit_discovered_today": round(projected, 2),
        "realized_profit": round(realized, 2),
        "projected_opportunity_per_dollar": projected_per,
        "realized_profit_per_dollar": realized_per,
        "base_cap_usd": BASE_CAP_USD,
        "current_tier": current_tier_name(),
        "current_cap_usd": current_tier_cap(),
        "boost_active": bool(targeting.get("active")),
        "boost_until": targeting.get("until") or "",
        "boost_targeting": targeting,
        "realized_unlock": realized_unlock_active(),
        "absolute_auto_max_usd": ABSOLUTE_AUTO_MAX_USD,
        "opportunity_boost_working": True,
        "realized_unlock_working": True,
    }
