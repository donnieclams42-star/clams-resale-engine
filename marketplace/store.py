from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from marketplace.catalog import CANARY_MARKET_IDS, CANARY_QUERIES, COMPARISON_PROVIDER, QUERY_PORTFOLIO, SCAN_MARKETS, miles_to_km
from marketplace.fingerprints import classify_lifecycle, hard_key, soft_fingerprint
from marketplace.models import ScanTarget
from marketplace.normalize import utc_now

_lock = threading.Lock()
_DB_PATH = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS marketplace_scan_markets (
    id TEXT PRIMARY KEY,
    name TEXT,
    location TEXT,
    country TEXT,
    currency TEXT,
    latitude REAL,
    longitude REAL,
    radius_miles INTEGER,
    region TEXT,
    enabled INTEGER DEFAULT 1,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_scan_targets (
    id TEXT PRIMARY KEY,
    name TEXT,
    enabled INTEGER DEFAULT 0,
    provider TEXT,
    query TEXT,
    product_family TEXT,
    query_type TEXT,
    market_id TEXT,
    location TEXT,
    radius_miles INTEGER,
    radius_km INTEGER,
    currency TEXT,
    country TEXT,
    cadence_tier TEXT,
    result_limit INTEGER,
    minimum_price REAL,
    maximum_price REAL,
    condition TEXT,
    delivery TEXT,
    listing_age_days INTEGER,
    last_started_at TEXT,
    last_success_at TEXT,
    next_due_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    cost_budget REAL,
    priority INTEGER,
    health_status TEXT,
    is_canary INTEGER DEFAULT 0,
    latitude REAL,
    longitude REAL,
    unique_listing_count INTEGER DEFAULT 0,
    candidate_count INTEGER DEFAULT 0,
    duplicate_ratio REAL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_scan_runs (
    id TEXT PRIMARY KEY,
    target_id TEXT,
    provider TEXT,
    actor TEXT,
    task_id TEXT,
    stage TEXT,
    status TEXT,
    apify_run_id TEXT,
    dataset_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    raw_row_count INTEGER DEFAULT 0,
    unique_count INTEGER DEFAULT 0,
    candidate_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    malformed_count INTEGER DEFAULT 0,
    usage_usd REAL,
    error_code TEXT,
    error_message TEXT,
    ingested INTEGER DEFAULT 0,
    extra_json TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_raw_events (
    id TEXT PRIMARY KEY,
    run_id TEXT,
    provider TEXT,
    dataset_id TEXT,
    source_listing_id TEXT,
    payload_json TEXT,
    observed_at TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id TEXT PRIMARY KEY,
    source TEXT,
    source_listing_id TEXT,
    canonical_url TEXT,
    title TEXT,
    normalized_title TEXT,
    display_price TEXT,
    asking_price REAL,
    currency TEXT,
    location_text TEXT,
    market_id TEXT,
    country TEXT,
    thumbnail_url TEXT,
    category TEXT,
    condition TEXT,
    seller_visible_id TEXT,
    seller_visible_name TEXT,
    listing_created_at TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    availability_status TEXT,
    lifecycle_status TEXT,
    provider TEXT,
    provider_run_id TEXT,
    provider_dataset_id TEXT,
    discovery_query TEXT,
    raw_payload_json TEXT,
    hard_fingerprint TEXT,
    soft_fingerprint TEXT,
    price_is_placeholder INTEGER,
    candidate_product_family TEXT,
    candidate_model TEXT,
    identity_confidence TEXT,
    stage1_status TEXT,
    stage1_reasons TEXT,
    stage1_priority INTEGER,
    details_scraped INTEGER DEFAULT 0,
    detail_fetched_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE(source, source_listing_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mp_listings_hard ON marketplace_listings(hard_fingerprint);
CREATE INDEX IF NOT EXISTS idx_mp_listings_url ON marketplace_listings(canonical_url);
CREATE INDEX IF NOT EXISTS idx_mp_listings_soft ON marketplace_listings(soft_fingerprint);
CREATE TABLE IF NOT EXISTS marketplace_listing_observations (
    id TEXT PRIMARY KEY,
    listing_id TEXT,
    run_id TEXT,
    observed_at TEXT,
    asking_price REAL,
    currency TEXT,
    lifecycle_status TEXT,
    title TEXT,
    location_text TEXT,
    provider TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_price_events (
    id TEXT PRIMARY KEY,
    listing_id TEXT,
    observed_at TEXT,
    old_price REAL,
    new_price REAL,
    currency TEXT,
    source_run_id TEXT,
    event_type TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_alert_events (
    id TEXT PRIMARY KEY,
    listing_id TEXT,
    alert_type TEXT,
    payload_json TEXT,
    created_at TEXT,
    sent_at TEXT,
    channel TEXT,
    skip_reason TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_provider_health (
    provider TEXT PRIMARY KEY,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    last_latency_ms INTEGER,
    malformed_row_rate REAL,
    missing_id_rate REAL,
    missing_price_rate REAL,
    last_usage_usd REAL,
    enabled INTEGER DEFAULT 1,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_webhook_events (
    id TEXT PRIMARY KEY,
    event_type TEXT,
    apify_run_id TEXT,
    payload_json TEXT,
    received_at TEXT,
    processed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS marketplace_kv (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS deal_verdicts (
    listing_id TEXT PRIMARY KEY,
    source TEXT,
    classification TEXT,
    expected_profit REAL,
    roi_pct REAL,
    landed_cost REAL,
    net_resale REAL,
    expected_resale REAL,
    fees REAL,
    shipping REAL,
    max_buy_price REAL,
    risk TEXT,
    liquidity TEXT,
    confidence TEXT,
    comp_source TEXT,
    sold_count INTEGER,
    reasons_json TEXT,
    signals_json TEXT,
    identity_confidence TEXT,
    candidate_model TEXT,
    candidate_product_family TEXT,
    analyzed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_deal_verdicts_class ON deal_verdicts(classification);
CREATE TABLE IF NOT EXISTS deal_comps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT,
    title TEXT,
    price REAL,
    url TEXT,
    sold_at TEXT,
    source TEXT,
    match_quality TEXT
);
CREATE TABLE IF NOT EXISTS ebay_sniper_runs (
    id TEXT PRIMARY KEY,
    query TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    raw_row_count INTEGER DEFAULT 0,
    unique_count INTEGER DEFAULT 0,
    candidate_count INTEGER DEFAULT 0,
    error_message TEXT
);
"""


def init_store(cache_dir: str) -> str:
    global _DB_PATH
    os.makedirs(cache_dir, exist_ok=True)
    _DB_PATH = os.path.join(cache_dir, "marketplace_scanner.db")
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)
    return _DB_PATH


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _connect() as conn:
        conn.executescript(SCHEMA)
        _migrate_schema(conn)


@contextmanager
def _connect():
    if not _DB_PATH:
        raise RuntimeError("Marketplace store is not initialized")
    with _lock:
        conn = sqlite3.connect(_DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


connect = _connect


def _row(row: sqlite3.Row | None) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _json_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _migrate_schema(conn: sqlite3.Connection) -> None:
    def _ensure(table: str, name: str, ddl: str) -> None:
        cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
        if name not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

    _ensure("deal_comps", "shipping", "REAL")
    _ensure("deal_comps", "condition", "TEXT")
    _ensure("deal_comps", "source_comp_id", "TEXT")
    _ensure("deal_comps", "variant", "TEXT")
    _ensure("deal_comps", "retrieved_at", "TEXT")
    _ensure("deal_comps", "include_decision", "TEXT")
    _ensure("deal_verdicts", "inbound_shipping", "REAL")
    _ensure("deal_verdicts", "sold_comp_state", "TEXT")
    _ensure("deal_verdicts", "discount_pct", "REAL")
    _ensure("deal_verdicts", "verification_required", "INTEGER")
    _ensure("marketplace_listings", "inbound_shipping", "REAL")
    _ensure("marketplace_listings", "local_pickup", "INTEGER")
    _ensure("marketplace_listings", "best_offer", "INTEGER")
    _ensure("deal_verdicts", "valuation_grade", "TEXT")
    _ensure("deal_verdicts", "verified_exit_basis", "TEXT")
    _ensure("deal_verdicts", "fast_cash", "REAL")
    _ensure("deal_verdicts", "exit_floor", "REAL")
    _ensure("deal_verdicts", "market_expectation", "REAL")
    _ensure("deal_verdicts", "provider_badges_json", "TEXT")
    _ensure("deal_verdicts", "why_json", "TEXT")
    _ensure("deal_verdicts", "best_expected_exit", "TEXT")
    _ensure("deal_verdicts", "source_to_exit", "TEXT")
    _ensure("deal_verdicts", "profit_velocity", "REAL")
    _ensure("deal_verdicts", "conservative_active_exit", "REAL")
    _ensure("deal_verdicts", "margin_of_safety_dollars", "REAL")
    _ensure("deal_verdicts", "margin_of_safety_percent", "REAL")
    _ensure("deal_verdicts", "break_even_resale", "REAL")
    _ensure("deal_verdicts", "valuation_error_cushion_dollars", "REAL")
    _ensure("deal_verdicts", "valuation_error_cushion_percent", "REAL")
    _ensure("deal_verdicts", "clean_comparable_count", "INTEGER")
    _ensure("deal_verdicts", "raw_comparable_count", "INTEGER")
    _ensure("deal_verdicts", "excluded_comparable_count", "INTEGER")
    _ensure("deal_verdicts", "market_stability", "TEXT")
    _ensure("deal_verdicts", "market_sample_confidence", "TEXT")
    _ensure("deal_verdicts", "valuation_basis", "TEXT")
    _ensure("deal_verdicts", "why_this_deal", "TEXT")
    _ensure("deal_verdicts", "first_profit_priority", "REAL")
    _ensure("deal_verdicts", "active_p25", "REAL")
    _ensure("deal_verdicts", "active_haircut", "REAL")
    _ensure("deal_verdicts", "expected_net", "REAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS valuation_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT,
            provider TEXT,
            evidence_type TEXT,
            grade TEXT,
            value REAL,
            currency TEXT,
            sample_count INTEGER,
            is_realized_sale INTEGER,
            is_active_ask INTEGER,
            payload_json TEXT,
            retrieved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_cache (
            cache_key TEXT PRIMARY KEY,
            evidence_json TEXT,
            retrieved_at TEXT,
            expires_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_provider_health (
            provider TEXT PRIMARY KEY,
            status TEXT,
            message TEXT,
            extra_json TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_own_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT,
            canonical_product_id TEXT,
            exact_model TEXT,
            variant TEXT,
            condition TEXT,
            purchase_price REAL,
            purchase_shipping REAL,
            purchase_fees REAL,
            repair REAL,
            sale_platform TEXT,
            sale_price REAL,
            sale_shipping REAL,
            sale_fees REAL,
            net_proceeds REAL,
            profit REAL,
            days_held REAL,
            location TEXT,
            purchased_at TEXT,
            sold_at TEXT,
            notes TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_manual_refs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            canonical_product_id TEXT,
            date_range TEXT,
            average_sold_price REAL,
            sold_low REAL,
            sold_high REAL,
            average_shipping REAL,
            sell_through REAL,
            sample_count INTEGER,
            research_at TEXT,
            notes TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_query_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            query TEXT,
            category TEXT,
            runs INTEGER DEFAULT 0,
            raw_rows INTEGER DEFAULT 0,
            unique_rows INTEGER DEFAULT 0,
            candidates INTEGER DEFAULT 0,
            deep INTEGER DEFAULT 0,
            monster INTEGER DEFAULT 0,
            hot INTEGER DEFAULT 0,
            strong INTEGER DEFAULT 0,
            purchases INTEGER DEFAULT 0,
            actual_profit REAL DEFAULT 0,
            provider_cost REAL DEFAULT 0,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_alert_dry_run (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT,
            classification TEXT,
            payload TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS valuation_family_stats (
            family TEXT PRIMARY KEY,
            deals_detected INTEGER DEFAULT 0,
            deals_reviewed INTEGER DEFAULT 0,
            purchases INTEGER DEFAULT 0,
            sales INTEGER DEFAULT 0,
            median_acquisition_discount REAL,
            expected_profit REAL,
            actual_profit REAL,
            predicted_resale REAL,
            actual_resale REAL,
            prediction_error REAL,
            days_to_sell REAL,
            problem_rate REAL,
            updated_at TEXT
        );
        """
    )
    try:
        from dealbrain.valuation.pricecharting.catalog import SCHEMA as PC_SCHEMA
        conn.executescript(PC_SCHEMA)
    except Exception:
        pass
    for stmt in (
        "ALTER TABLE valuation_query_stats ADD COLUMN pricecharting_matches INTEGER DEFAULT 0",
        "ALTER TABLE valuation_query_stats ADD COLUMN valuation_conflicts INTEGER DEFAULT 0",
        "ALTER TABLE valuation_query_stats ADD COLUMN stage1 INTEGER DEFAULT 0",
        "ALTER TABLE valuation_query_stats ADD COLUMN stage2 INTEGER DEFAULT 0",
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass


def disable_all_scan_targets() -> int:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE marketplace_scan_targets SET enabled = 0, updated_at = ? WHERE enabled = 1",
            (utc_now(),),
        )
        return int(cur.rowcount or 0)


def enable_first_profit_level1_targets(provider: str = "rigelbytes") -> dict[str, Any]:
    from marketplace.catalog import (
        COMPARISON_PROVIDER,
        PRECISION_RESULT_LIMIT,
        TREASURE_RESULT_LIMIT,
        first_profit_facebook_precision_queries,
        first_profit_facebook_treasure_queries,
        first_profit_level1_markets,
        miles_to_km,
    )

    now = utc_now()
    disabled = disable_all_scan_targets()
    enabled_ids: list[str] = []
    precision_count = 0
    treasure_count = 0
    with _connect() as conn:
        conn.execute(
            "UPDATE marketplace_scan_targets SET enabled = 0, updated_at = ? WHERE provider = ?",
            (now, COMPARISON_PROVIDER),
        )
        for market in first_profit_level1_markets():
            conn.execute(
                """INSERT INTO marketplace_scan_markets
                (id, name, location, country, currency, latitude, longitude, radius_miles, region, enabled, created_at, updated_at)
                VALUES (?, ?, ?, 'US', 'USD', ?, ?, ?, 'northeast', 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, location=excluded.location, latitude=excluded.latitude,
                longitude=excluded.longitude, radius_miles=excluded.radius_miles, enabled=1, updated_at=excluded.updated_at""",
                (
                    market["id"], market["name"], market["location"], market["latitude"], market["longitude"],
                    market["radius_miles"], now, now,
                ),
            )
            radius = int(market["radius_miles"])
            radius_km = miles_to_km(radius)
            for query in first_profit_facebook_precision_queries():
                target_id = f"fp1:{provider}:{market['id']}:PRECISION:{query['query']}".replace(" ", "-")[:80]
                priority = int(market["priority_base"]) + int(query.get("priority") or 20)
                _upsert_level1_target(
                    conn,
                    target_id=target_id,
                    name=f"{market['name']} · {query['query']}",
                    provider=provider,
                    query=query["query"],
                    product_family=query.get("product_family") or "",
                    query_type=query.get("query_type") or "EXACT_MODEL",
                    market=market,
                    radius=radius,
                    radius_km=radius_km,
                    cadence="PRECISION",
                    result_limit=PRECISION_RESULT_LIMIT,
                    listing_age_days=1,
                    priority=priority,
                    now=now,
                )
                enabled_ids.append(target_id)
                precision_count += 1
            for query in first_profit_facebook_treasure_queries():
                target_id = f"fp1:{provider}:{market['id']}:TREASURE:{query['query']}".replace(" ", "-")[:80]
                priority = 70 + int(market["priority_base"]) + int(query.get("priority") or 30)
                _upsert_level1_target(
                    conn,
                    target_id=target_id,
                    name=f"{market['name']} · treasure · {query['query']}",
                    provider=provider,
                    query=query["query"],
                    product_family=query.get("product_family") or "",
                    query_type=query.get("query_type") or "GENERIC",
                    market=market,
                    radius=radius,
                    radius_km=radius_km,
                    cadence="TREASURE",
                    result_limit=TREASURE_RESULT_LIMIT,
                    listing_age_days=7,
                    priority=priority,
                    now=now,
                )
                enabled_ids.append(target_id)
                treasure_count += 1
    return {
        "ok": True,
        "disabled": disabled,
        "enabled": len(enabled_ids),
        "precision_targets": precision_count,
        "treasure_targets": treasure_count,
        "markets": [row["id"] for row in first_profit_level1_markets()],
    }


def _upsert_level1_target(
    conn,
    *,
    target_id: str,
    name: str,
    provider: str,
    query: str,
    product_family: str,
    query_type: str,
    market: dict[str, Any],
    radius: int,
    radius_km: int,
    cadence: str,
    result_limit: int,
    listing_age_days: int,
    priority: int,
    now: str,
) -> None:
    existing = conn.execute("SELECT id FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone()
    if existing:
        conn.execute(
            """UPDATE marketplace_scan_targets SET enabled=1, name=?, query=?, product_family=?, query_type=?,
            market_id=?, location=?, radius_miles=?, radius_km=?, cadence_tier=?, result_limit=?, listing_age_days=?,
            priority=?, health_status='idle', consecutive_failures=0, is_canary=0, latitude=?, longitude=?,
            provider=?, updated_at=? WHERE id=?""",
            (
                name, query, product_family, query_type, market["id"], market["location"], radius, radius_km,
                cadence, result_limit, listing_age_days, priority, market["latitude"], market["longitude"],
                provider, now, target_id,
            ),
        )
        return
    conn.execute(
        """INSERT INTO marketplace_scan_targets
        (id, name, enabled, provider, query, product_family, query_type, market_id, location, radius_miles, radius_km,
         currency, country, cadence_tier, result_limit, minimum_price, maximum_price, condition, delivery, listing_age_days,
         last_started_at, last_success_at, next_due_at, consecutive_failures, cost_budget, priority, health_status,
         is_canary, latitude, longitude, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 'USD', 'US', ?, ?, NULL, NULL, '', '', ?, '', '', '', 0, 0, ?, 'idle', 0, ?, ?, ?, ?)""",
        (
            target_id, name, provider, query, product_family, query_type, market["id"], market["location"],
            radius, radius_km, cadence, result_limit, listing_age_days, priority, market["latitude"],
            market["longitude"], now, now,
        ),
    )


def seed_defaults(provider: str = "rigelbytes") -> None:
    now = utc_now()
    with _connect() as conn:
        for market in SCAN_MARKETS:
            conn.execute(
                """INSERT INTO marketplace_scan_markets
                (id, name, location, country, currency, latitude, longitude, radius_miles, region, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name, location=excluded.location, latitude=excluded.latitude,
                longitude=excluded.longitude, radius_miles=excluded.radius_miles, updated_at=excluded.updated_at""",
                (
                    market["id"], market["name"], market["location"], market["country"], market["currency"],
                    market["latitude"], market["longitude"], market["radius_miles"], market["region"], now, now,
                ),
            )
        for market in SCAN_MARKETS:
            if market["id"] not in CANARY_MARKET_IDS:
                continue
            for query in QUERY_PORTFOLIO:
                is_canary = query["query"] in CANARY_QUERIES
                target_id = f"{provider}:{market['id']}:{query['query_type']}:{query['query']}".replace(" ", "-")[:80]
                existing = conn.execute("SELECT id FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone()
                if existing:
                    continue
                enabled = 0
                cadence = "NORMAL"
                if is_canary:
                    cadence = "HOT" if query["query"] in {"iphone 15 pro", "ps5"} else "NORMAL"
                conn.execute(
                    """INSERT INTO marketplace_scan_targets
                    (id, name, enabled, provider, query, product_family, query_type, market_id, location, radius_miles, radius_km,
                     currency, country, cadence_tier, result_limit, minimum_price, maximum_price, condition, delivery, listing_age_days,
                     last_started_at, last_success_at, next_due_at, consecutive_failures, cost_budget, priority, health_status,
                     is_canary, latitude, longitude, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', '', 0, 0, ?, 'idle', ?, ?, ?, ?, ?)""",
                    (
                        target_id,
                        f"{market['name']} · {query['query']}",
                        enabled,
                        provider,
                        query["query"],
                        query["product_family"],
                        query["query_type"],
                        market["id"],
                        market["location"],
                        market["radius_miles"],
                        miles_to_km(market["radius_miles"]),
                        market["currency"],
                        market["country"],
                        cadence,
                        8 if is_canary else 12,
                        None,
                        None,
                        "",
                        "",
                        1 if is_canary else 7,
                        int(query.get("priority") or 100),
                        1 if is_canary else 0,
                        market["latitude"],
                        market["longitude"],
                        now,
                        now,
                    ),
                )
        for market_id in CANARY_MARKET_IDS:
            market = next((item for item in SCAN_MARKETS if item["id"] == market_id), None)
            if not market:
                continue
            for query_text in CANARY_QUERIES:
                query = next((item for item in QUERY_PORTFOLIO if item["query"] == query_text), None)
                if not query:
                    continue
                target_id = f"{COMPARISON_PROVIDER}:{market['id']}:EXACT:{query_text}".replace(" ", "-")[:80]
                existing = conn.execute("SELECT id FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone()
                if existing:
                    continue
                conn.execute(
                    """INSERT INTO marketplace_scan_targets
                    (id, name, enabled, provider, query, product_family, query_type, market_id, location, radius_miles, radius_km,
                     currency, country, cadence_tier, result_limit, minimum_price, maximum_price, condition, delivery, listing_age_days,
                     last_started_at, last_success_at, next_due_at, consecutive_failures, cost_budget, priority, health_status,
                     is_canary, latitude, longitude, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'LOW', 8, NULL, NULL, '', '', 1, '', '', '', 0, 0, 200, 'idle', 1, ?, ?, ?, ?)""",
                    (
                        target_id,
                        f"K1ra compare · {market['name']} · {query_text}",
                        COMPARISON_PROVIDER,
                        query_text,
                        query["product_family"],
                        query["query_type"],
                        market["id"],
                        market["location"],
                        market["radius_miles"],
                        miles_to_km(market["radius_miles"]),
                        market["currency"],
                        market["country"],
                        market["latitude"],
                        market["longitude"],
                        now,
                        now,
                    ),
                )
        try:
            from dealbrain.valuation.pricecharting.queries import level1_query_pack
            packs = level1_query_pack()
        except Exception:
            packs = []
        for market in SCAN_MARKETS:
            if market["id"] not in CANARY_MARKET_IDS:
                continue
            for query in packs:
                target_id = f"level1:{market['id']}:{query.get('lane')}:{query['query']}".replace(" ", "-")[:80]
                existing = conn.execute("SELECT id FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone()
                if existing:
                    continue
                conn.execute(
                    """INSERT INTO marketplace_scan_targets
                    (id, name, enabled, provider, query, product_family, query_type, market_id, location, radius_miles, radius_km,
                     currency, country, cadence_tier, result_limit, minimum_price, maximum_price, condition, delivery, listing_age_days,
                     last_started_at, last_success_at, next_due_at, consecutive_failures, cost_budget, priority, health_status,
                     is_canary, latitude, longitude, created_at, updated_at)
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NORMAL', 8, NULL, NULL, '', '', 7, '', '', '', 0, 0, ?, 'idle', 0, ?, ?, ?, ?)""",
                    (
                        target_id,
                        f"Level 1 Retro · {query['query']}",
                        provider,
                        query["query"],
                        query.get("product_family") or "retro-nintendo",
                        query.get("query_type") or "GENERIC",
                        market["id"],
                        market["location"],
                        market["radius_miles"],
                        miles_to_km(market["radius_miles"]),
                        market["currency"],
                        market["country"],
                        int(query.get("priority") or 40),
                        market["latitude"],
                        market["longitude"],
                        now,
                        now,
                    ),
                )


def row_to_target(row: dict[str, Any]) -> ScanTarget:
    return ScanTarget(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or ""),
        enabled=bool(int(row.get("enabled") or 0)),
        provider=str(row.get("provider") or "rigelbytes"),
        query=str(row.get("query") or ""),
        product_family=str(row.get("product_family") or ""),
        query_type=str(row.get("query_type") or "GENERIC"),
        market_id=str(row.get("market_id") or ""),
        location=str(row.get("location") or ""),
        radius_miles=int(row.get("radius_miles") or 40),
        radius_km=int(row.get("radius_km") or miles_to_km(row.get("radius_miles") or 40)),
        currency=str(row.get("currency") or "USD"),
        country=str(row.get("country") or "US"),
        cadence_tier=str(row.get("cadence_tier") or "NORMAL"),
        result_limit=int(row.get("result_limit") or 12),
        minimum_price=row.get("minimum_price"),
        maximum_price=row.get("maximum_price"),
        condition=str(row.get("condition") or ""),
        delivery=str(row.get("delivery") or ""),
        listing_age_days=row.get("listing_age_days"),
        last_started_at=str(row.get("last_started_at") or ""),
        last_success_at=str(row.get("last_success_at") or ""),
        next_due_at=str(row.get("next_due_at") or ""),
        consecutive_failures=int(row.get("consecutive_failures") or 0),
        cost_budget=float(row.get("cost_budget") or 0),
        priority=int(row.get("priority") or 100),
        health_status=str(row.get("health_status") or "idle"),
        is_canary=bool(int(row.get("is_canary") or 0)),
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
    )


def list_targets(enabled_only: bool = False, canary_only: bool = False, provider: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM marketplace_scan_targets WHERE 1=1"
    args: list[Any] = []
    if enabled_only:
        sql += " AND enabled = 1"
    if canary_only:
        sql += " AND is_canary = 1"
    if provider:
        sql += " AND provider = ?"
        args.append(provider)
    sql += " ORDER BY priority ASC, name COLLATE NOCASE"
    with _connect() as conn:
        return [_row(row) for row in conn.execute(sql, args)]


def get_target(target_id: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone())


def active_run_for_target(target_id: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM marketplace_scan_runs WHERE target_id = ? AND status IN ('PENDING','RUNNING','READY','CREATED') ORDER BY started_at DESC LIMIT 1",
            (target_id,),
        ).fetchone())


def create_scan_run(target: ScanTarget | dict[str, Any], *, stage: str, provider: str, actor: str = "", task_id: str = "") -> str:
    run_id = uuid.uuid4().hex
    target_id = target.id if isinstance(target, ScanTarget) else str(target.get("id") or "")
    now = utc_now()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO marketplace_scan_runs
            (id, target_id, provider, actor, task_id, stage, status, apify_run_id, dataset_id, started_at, extra_json)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', '', '', ?, '{}')""",
            (run_id, target_id, provider, actor, task_id, stage, now),
        )
        conn.execute(
            "UPDATE marketplace_scan_targets SET last_started_at = ?, health_status = 'running', updated_at = ? WHERE id = ?",
            (now, now, target_id),
        )
    return run_id


def mark_run_started(run_id: str, *, apify_run_id: str, dataset_id: str = "", actor: str = "", status: str = "RUNNING") -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE marketplace_scan_runs SET status = ?, apify_run_id = ?, dataset_id = COALESCE(NULLIF(?, ''), dataset_id), actor = COALESCE(NULLIF(?, ''), actor)
            WHERE id = ?""",
            (status, apify_run_id, dataset_id, actor, run_id),
        )


def get_run(run_id: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_scan_runs WHERE id = ?", (run_id,)).fetchone())


def get_run_by_apify_id(apify_run_id: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_scan_runs WHERE apify_run_id = ? ORDER BY started_at DESC LIMIT 1", (apify_run_id,)).fetchone())


def list_stale_runs(stale_seconds: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        return [_row(row) for row in conn.execute(
            """SELECT * FROM marketplace_scan_runs
               WHERE ingested = 0
               AND status IN ('PENDING','RUNNING','READY','CREATED')
               AND apify_run_id IS NOT NULL AND apify_run_id != ''
               ORDER BY started_at ASC LIMIT 10"""
        )]


def finish_run(run_id: str, **fields: Any) -> None:
    assignments = ["finished_at = ?"]
    values: list[Any] = [utc_now()]
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        values.append(value)
    values.append(run_id)
    with _connect() as conn:
        conn.execute(f"UPDATE marketplace_scan_runs SET {', '.join(assignments)} WHERE id = ?", values)


def record_target_success(target_id: str, next_due_at: str, **metrics: Any) -> None:
    now = utc_now()
    with _connect() as conn:
        conn.execute(
            """UPDATE marketplace_scan_targets SET last_success_at = ?, next_due_at = ?, consecutive_failures = 0,
            health_status = 'ok', unique_listing_count = COALESCE(unique_listing_count,0) + ?,
            candidate_count = COALESCE(candidate_count,0) + ?, updated_at = ? WHERE id = ?""",
            (now, next_due_at, int(metrics.get("unique_count") or 0), int(metrics.get("candidate_count") or 0), now, target_id),
        )


def record_target_failure(target_id: str, *, breaker: int, retry_seconds: int) -> dict[str, Any]:
    now = utc_now()
    with _connect() as conn:
        row = _row(conn.execute("SELECT consecutive_failures FROM marketplace_scan_targets WHERE id = ?", (target_id,)).fetchone())
        failures = int(row.get("consecutive_failures") or 0) + 1
        paused = failures >= max(1, breaker)
        next_due = ""
        health = "degraded"
        if paused:
            health = "paused"
            next_due = (datetime.now(timezone.utc) + timedelta(seconds=max(60, retry_seconds))).replace(microsecond=0).isoformat()
        conn.execute(
            """UPDATE marketplace_scan_targets SET consecutive_failures = ?, health_status = ?, next_due_at = ?, updated_at = ? WHERE id = ?""",
            (failures, health, next_due, now, target_id),
        )
        return {"consecutive_failures": failures, "paused": paused, "health": health}


def remember_webhook(event_id: str, event_type: str, apify_run_id: str, payload: dict[str, Any]) -> bool:
    with _connect() as conn:
        existing = conn.execute("SELECT id FROM marketplace_webhook_events WHERE id = ?", (event_id,)).fetchone()
        if existing:
            return False
        conn.execute(
            """INSERT INTO marketplace_webhook_events (id, event_type, apify_run_id, payload_json, received_at, processed)
            VALUES (?, ?, ?, ?, ?, 0)""",
            (event_id, event_type, apify_run_id, json.dumps(payload, default=str)[:20000], utc_now()),
        )
        return True


def mark_webhook_processed(event_id: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE marketplace_webhook_events SET processed = 1 WHERE id = ?", (event_id,))


def append_raw_event(run_id: str, provider: str, dataset_id: str, source_listing_id: str, payload: dict[str, Any]) -> str:
    event_id = uuid.uuid4().hex
    with _connect() as conn:
        conn.execute(
            """INSERT INTO marketplace_raw_events (id, run_id, provider, dataset_id, source_listing_id, payload_json, observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (event_id, run_id, provider, dataset_id, source_listing_id, json.dumps(payload, default=str)[:24000], utc_now()),
        )
    return event_id


def listing_by_id(listing_id: str) -> dict[str, Any]:
    if not listing_id:
        return {}
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_listings WHERE id = ?", (listing_id,)).fetchone())


def price_events(listing_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = [_row(row) for row in conn.execute(
            "SELECT * FROM marketplace_price_events WHERE listing_id = ? ORDER BY observed_at DESC",
            (listing_id,),
        )]
    for row in rows:
        row["asking_price"] = row.get("new_price")
        row["recorded_at"] = row.get("observed_at")
    return rows


def listing_by_hard(source: str, source_listing_id: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM marketplace_listings WHERE source = ? AND source_listing_id = ?",
            (source, source_listing_id),
        ).fetchone())


def listing_by_url(url: str) -> dict[str, Any]:
    if not url:
        return {}
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_listings WHERE canonical_url = ? LIMIT 1", (url,)).fetchone())


def listing_by_soft(fingerprint: str) -> dict[str, Any]:
    if not fingerprint:
        return {}
    with _connect() as conn:
        return _row(conn.execute(
            "SELECT * FROM marketplace_listings WHERE soft_fingerprint = ? ORDER BY last_seen_at DESC LIMIT 1",
            (fingerprint,),
        ).fetchone())


def upsert_listing(listing: dict[str, Any], run_id: str, seen_duplicate_hours: int = 6) -> tuple[dict[str, Any], str, bool]:
    source = listing.get("source") or "facebook_marketplace"
    source_id = str(listing.get("source_listing_id") or "")
    url = str(listing.get("canonical_url") or "")
    existing = listing_by_hard(source, source_id) if source_id else {}
    if not existing and url:
        existing = listing_by_url(url)
    fingerprint = soft_fingerprint(
        title=str(listing.get("normalized_title") or listing.get("title") or ""),
        price=listing.get("asking_price"),
        location=str(listing.get("location_text") or ""),
        seller=str(listing.get("seller_visible_id") or listing.get("seller_visible_name") or ""),
    )
    if not existing:
        existing = listing_by_soft(fingerprint)
    is_new = not bool(existing)
    lifecycle = classify_lifecycle(existing, listing, seen_duplicate_hours=seen_duplicate_hours)
    now = utc_now()
    listing_id = str(existing.get("id") or uuid.uuid4().hex)
    hard = hard_key(source, source_id or url)
    payload = {
        "id": listing_id,
        "source": source,
        "source_listing_id": source_id,
        "canonical_url": url,
        "title": listing.get("title") or existing.get("title") or "",
        "normalized_title": listing.get("normalized_title") or existing.get("normalized_title") or "",
        "display_price": listing.get("display_price") or existing.get("display_price") or "",
        "asking_price": listing.get("asking_price") if listing.get("asking_price") is not None else existing.get("asking_price"),
        "currency": listing.get("currency") or existing.get("currency") or "USD",
        "location_text": listing.get("location_text") or existing.get("location_text") or "",
        "market_id": existing.get("market_id") or listing.get("market_id") or "",
        "country": listing.get("country") or existing.get("country") or "US",
        "thumbnail_url": listing.get("thumbnail_url") or existing.get("thumbnail_url") or "",
        "category": listing.get("category") or existing.get("category") or "",
        "condition": listing.get("condition") or existing.get("condition") or "",
        "seller_visible_id": listing.get("seller_visible_id") or existing.get("seller_visible_id") or "",
        "seller_visible_name": listing.get("seller_visible_name") or existing.get("seller_visible_name") or "",
        "listing_created_at": listing.get("listing_created_at") or existing.get("listing_created_at") or "",
        "first_seen_at": existing.get("first_seen_at") or now,
        "last_seen_at": now,
        "availability_status": listing.get("availability_status") or "live",
        "lifecycle_status": lifecycle,
        "provider": listing.get("provider") or existing.get("provider") or "",
        "provider_run_id": listing.get("provider_run_id") or run_id,
        "provider_dataset_id": listing.get("provider_dataset_id") or existing.get("provider_dataset_id") or "",
        "discovery_query": listing.get("discovery_query") or existing.get("discovery_query") or "",
        "raw_payload_json": listing.get("raw_payload") or existing.get("raw_payload_json") or "",
        "hard_fingerprint": hard,
        "soft_fingerprint": fingerprint,
        "price_is_placeholder": 1 if listing.get("price_is_placeholder") else 0,
        "inbound_shipping": listing.get("inbound_shipping") if listing.get("inbound_shipping") is not None else existing.get("inbound_shipping"),
        "local_pickup": 1 if listing.get("local_pickup") else 0,
        "best_offer": 1 if listing.get("best_offer") else 0,
        "candidate_product_family": listing.get("candidate_product_family") or existing.get("candidate_product_family") or "",
        "candidate_model": listing.get("candidate_model") or existing.get("candidate_model") or "",
        "identity_confidence": listing.get("identity_confidence") or existing.get("identity_confidence") or "",
        "stage1_status": listing.get("stage1_status") or existing.get("stage1_status") or "",
        "stage1_reasons": json.dumps(listing.get("stage1_reasons") or _json_list(existing.get("stage1_reasons"))),
        "stage1_priority": int(listing.get("stage1_priority") or existing.get("stage1_priority") or 0),
        "details_scraped": 1 if listing.get("details_scraped") or existing.get("details_scraped") else 0,
        "detail_fetched_at": existing.get("detail_fetched_at") or "",
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
    }
    columns = ",".join(payload.keys())
    placeholders = ",".join(f":{key}" for key in payload)
    updates = ",".join(f"{key}=excluded.{key}" for key in payload if key not in {"id", "first_seen_at", "created_at", "source", "source_listing_id", "market_id"})
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO marketplace_listings ({columns}) VALUES ({placeholders})
            ON CONFLICT(source, source_listing_id) DO UPDATE SET {updates}""",
            payload,
        )
        conn.execute(
            """INSERT INTO marketplace_listing_observations
            (id, listing_id, run_id, observed_at, asking_price, currency, lifecycle_status, title, location_text, provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, listing_id, run_id, now, payload["asking_price"], payload["currency"], lifecycle, payload["title"], payload["location_text"], payload["provider"]),
        )
        if lifecycle in {"NEW", "PRICE_DROP", "PRICE_INCREASE"} and payload["asking_price"] is not None:
            conn.execute(
                """INSERT INTO marketplace_price_events
                (id, listing_id, observed_at, old_price, new_price, currency, source_run_id, event_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (uuid.uuid4().hex, listing_id, now, existing.get("asking_price") if existing else None, payload["asking_price"], payload["currency"], run_id, lifecycle),
            )
    return listing_by_hard(source, source_id) or payload, lifecycle, is_new


def apply_stage1(listing_id: str, stage: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE marketplace_listings SET candidate_product_family = ?, candidate_model = ?, identity_confidence = ?,
            stage1_status = ?, stage1_reasons = ?, stage1_priority = ?, updated_at = ? WHERE id = ?""",
            (
                stage.get("candidate_product_family") or "",
                stage.get("candidate_model") or "",
                stage.get("identity_confidence") or "",
                stage.get("stage1_status") or "",
                json.dumps(stage.get("stage1_reasons") or []),
                int(stage.get("stage1_priority") or 0),
                utc_now(),
                listing_id,
            ),
        )


def mark_details_fetched(listing_ids: Iterable[str], run_id: str) -> None:
    now = utc_now()
    with _connect() as conn:
        for listing_id in listing_ids:
            conn.execute(
                "UPDATE marketplace_listings SET details_scraped = 1, detail_fetched_at = ?, provider_run_id = ?, updated_at = ? WHERE id = ?",
                (now, run_id, now, listing_id),
            )


def listings_needing_detail(limit: int = 3) -> list[dict[str, Any]]:
    with _connect() as conn:
        return [_row(row) for row in conn.execute(
            """SELECT * FROM marketplace_listings
            WHERE stage1_status = 'CANDIDATE' AND COALESCE(details_scraped,0) = 0
            AND lifecycle_status IN ('NEW','PRICE_DROP','RELISTED','UPDATED')
            ORDER BY stage1_priority DESC, last_seen_at DESC LIMIT ?""",
            (limit,),
        )]


def list_feed(filters: dict[str, Any] | None = None, limit: int = 60) -> list[dict[str, Any]]:
    filters = filters or {}
    sql = "SELECT * FROM marketplace_listings WHERE 1=1"
    args: list[Any] = []
    if filters.get("family"):
        sql += " AND candidate_product_family = ?"
        args.append(filters["family"])
    if filters.get("market"):
        sql += " AND market_id = ?"
        args.append(filters["market"])
    if filters.get("lifecycle"):
        sql += " AND lifecycle_status = ?"
        args.append(filters["lifecycle"])
    if filters.get("stage1"):
        sql += " AND stage1_status = ?"
        args.append(filters["stage1"])
    if filters.get("provider"):
        sql += " AND provider = ?"
        args.append(filters["provider"])
    sort = str(filters.get("sort") or "newest").lower()
    if sort == "price":
        sql += " ORDER BY CASE WHEN asking_price IS NULL THEN 1 ELSE 0 END, asking_price ASC"
    elif sort == "priority":
        sql += " ORDER BY COALESCE(stage1_priority,0) DESC, last_seen_at DESC"
    elif sort == "price_drop":
        sql += " ORDER BY CASE lifecycle_status WHEN 'PRICE_DROP' THEN 0 ELSE 1 END, last_seen_at DESC"
    else:
        sql += " ORDER BY last_seen_at DESC"
    sql += " LIMIT ?"
    args.append(limit)
    with _connect() as conn:
        rows = [_row(row) for row in conn.execute(sql, args)]
    for row in rows:
        row["stage1_reasons"] = _json_list(row.get("stage1_reasons"))
    return rows


def scanner_counts() -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).replace(microsecond=0).isoformat()
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _connect() as conn:
        listings_24h = conn.execute("SELECT COUNT(*) FROM marketplace_listings WHERE last_seen_at >= ?", (cutoff,)).fetchone()[0]
        unique_today = conn.execute("SELECT COUNT(*) FROM marketplace_listings WHERE first_seen_at LIKE ?", (f"{day}%",)).fetchone()[0]
        seen_today = conn.execute("SELECT COUNT(*) FROM marketplace_listings WHERE last_seen_at LIKE ?", (f"{day}%",)).fetchone()[0]
        new_count = conn.execute("SELECT COUNT(*) FROM marketplace_listings WHERE lifecycle_status = 'NEW'").fetchone()[0]
        candidates = conn.execute("SELECT COUNT(*) FROM marketplace_listings WHERE stage1_status = 'CANDIDATE'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM marketplace_scan_runs WHERE status IN ('PENDING','RUNNING','READY','CREATED')").fetchone()[0]
        failed_targets = conn.execute("SELECT COUNT(*) FROM marketplace_scan_targets WHERE health_status IN ('degraded','paused') OR consecutive_failures >= 3").fetchone()[0]
        last = _row(conn.execute("SELECT * FROM marketplace_scan_runs ORDER BY started_at DESC LIMIT 1").fetchone())
        last_discovery = _row(conn.execute(
            "SELECT * FROM marketplace_scan_runs WHERE COALESCE(stage,'discovery') != 'detail' ORDER BY started_at DESC LIMIT 1"
        ).fetchone())
        last_detail = _row(conn.execute(
            "SELECT * FROM marketplace_scan_runs WHERE stage = 'detail' ORDER BY started_at DESC LIMIT 1"
        ).fetchone())
        last_ok = _row(conn.execute(
            "SELECT * FROM marketplace_scan_runs WHERE COALESCE(stage,'discovery') != 'detail' AND status IN ('SUCCEEDED','completed','completed_zero') ORDER BY finished_at DESC LIMIT 1"
        ).fetchone())
        next_due = _row(conn.execute("SELECT next_due_at FROM marketplace_scan_targets WHERE enabled = 1 AND next_due_at != '' ORDER BY next_due_at ASC LIMIT 1").fetchone())
        enabled_markets = conn.execute("SELECT COUNT(DISTINCT market_id) FROM marketplace_scan_targets WHERE enabled = 1").fetchone()[0]
        precision_targets = conn.execute("SELECT COUNT(*) FROM marketplace_scan_targets WHERE enabled = 1 AND cadence_tier = 'PRECISION'").fetchone()[0]
        treasure_targets = conn.execute("SELECT COUNT(*) FROM marketplace_scan_targets WHERE enabled = 1 AND cadence_tier = 'TREASURE'").fetchone()[0]
        runs_today = conn.execute("SELECT COUNT(*) FROM marketplace_scan_runs WHERE started_at LIKE ?", (f"{day}%",)).fetchone()[0]
        raw_today = conn.execute("SELECT COALESCE(SUM(raw_row_count),0) FROM marketplace_scan_runs WHERE started_at LIKE ?", (f"{day}%",)).fetchone()[0]
        unique_run_today = conn.execute("SELECT COALESCE(SUM(unique_count),0) FROM marketplace_scan_runs WHERE started_at LIKE ?", (f"{day}%",)).fetchone()[0]
        dup_today = conn.execute("SELECT COALESCE(SUM(duplicate_count),0) FROM marketplace_scan_runs WHERE started_at LIKE ?", (f"{day}%",)).fetchone()[0]
        cand_today = conn.execute("SELECT COALESCE(SUM(candidate_count),0) FROM marketplace_scan_runs WHERE started_at LIKE ?", (f"{day}%",)).fetchone()[0]
    return {
        "listings_24h": listings_24h,
        "new_count": new_count,
        "candidates": candidates,
        "running": running,
        "failed_targets": failed_targets,
        "last_run": last,
        "last_discovery": last_discovery,
        "last_detail": last_detail,
        "last_success": last_ok,
        "next_due_at": (next_due or {}).get("next_due_at") or "",
        "enabled_markets": enabled_markets,
        "precision_targets": precision_targets,
        "treasure_targets": treasure_targets,
        "runs_today": runs_today,
        "seen_today": seen_today,
        "unique_today": unique_today,
        "raw_today": raw_today,
        "unique_run_today": unique_run_today,
        "duplicate_today": dup_today,
        "candidates_today": cand_today,
    }


def running_discovery_run() -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute(
            """SELECT * FROM marketplace_scan_runs
            WHERE status IN ('PENDING','RUNNING','READY','CREATED')
            AND COALESCE(stage,'discovery') != 'detail'
            ORDER BY started_at DESC LIMIT 1"""
        ).fetchone())


def due_targets_for_market(market_id: str, limit: int = 1, cadence: str = "") -> list[dict[str, Any]]:
    now = utc_now()
    sql = """SELECT * FROM marketplace_scan_targets
            WHERE enabled = 1 AND market_id = ?
            AND (next_due_at IS NULL OR next_due_at = '' OR next_due_at <= ?)
            AND (health_status != 'paused' OR next_due_at <= ?)"""
    args: list[Any] = [market_id, now, now]
    if cadence:
        sql += " AND UPPER(cadence_tier) = ?"
        args.append(str(cadence).upper())
    sql += " ORDER BY priority ASC, last_success_at ASC LIMIT ?"
    args.append(limit)
    with _connect() as conn:
        return [_row(row) for row in conn.execute(sql, args)]


def update_provider_health(provider: str, *, success: bool, malformed_rate: float = 0, missing_id_rate: float = 0, missing_price_rate: float = 0, usage_usd: float | None = None, latency_ms: int | None = None) -> None:
    now = utc_now()
    with _connect() as conn:
        row = _row(conn.execute("SELECT * FROM marketplace_provider_health WHERE provider = ?", (provider,)).fetchone())
        success_count = int(row.get("success_count") or 0) + (1 if success else 0)
        failure_count = int(row.get("failure_count") or 0) + (0 if success else 1)
        consecutive = 0 if success else int(row.get("consecutive_failures") or 0) + 1
        conn.execute(
            """INSERT INTO marketplace_provider_health
            (provider, success_count, failure_count, last_success_at, last_failure_at, consecutive_failures, last_latency_ms,
             malformed_row_rate, missing_id_rate, missing_price_rate, last_usage_usd, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(provider) DO UPDATE SET
            success_count=excluded.success_count, failure_count=excluded.failure_count,
            last_success_at=excluded.last_success_at, last_failure_at=excluded.last_failure_at,
            consecutive_failures=excluded.consecutive_failures, last_latency_ms=excluded.last_latency_ms,
            malformed_row_rate=excluded.malformed_row_rate, missing_id_rate=excluded.missing_id_rate,
            missing_price_rate=excluded.missing_price_rate, last_usage_usd=excluded.last_usage_usd, updated_at=excluded.updated_at""",
            (
                provider,
                success_count,
                failure_count,
                now if success else row.get("last_success_at") or "",
                now if not success else row.get("last_failure_at") or "",
                consecutive,
                latency_ms,
                malformed_rate,
                missing_id_rate,
                missing_price_rate,
                usage_usd,
                now,
            ),
        )


def get_provider_health(provider: str) -> dict[str, Any]:
    with _connect() as conn:
        return _row(conn.execute("SELECT * FROM marketplace_provider_health WHERE provider = ?", (provider,)).fetchone())


def due_targets(limit: int = 3) -> list[dict[str, Any]]:
    now = utc_now()
    with _connect() as conn:
        rows = [_row(row) for row in conn.execute(
            """SELECT * FROM marketplace_scan_targets
            WHERE enabled = 1
            AND (next_due_at IS NULL OR next_due_at = '' OR next_due_at <= ?)
            AND (health_status != 'paused' OR next_due_at <= ?)
            ORDER BY priority ASC, last_success_at ASC LIMIT ?""",
            (now, now, limit),
        )]
    return rows


def set_target_enabled(target_id: str, enabled: bool) -> None:
    with _connect() as conn:
        conn.execute("UPDATE marketplace_scan_targets SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, utc_now(), target_id))


def enable_canary_targets(provider: str = "rigelbytes") -> list[str]:
    ids = []
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id FROM marketplace_scan_targets WHERE is_canary = 1 AND provider = ?",
            (provider,),
        ).fetchall()
        for row in rows:
            conn.execute("UPDATE marketplace_scan_targets SET enabled = 1, health_status = 'idle', consecutive_failures = 0, updated_at = ? WHERE id = ?", (utc_now(), row["id"]))
            ids.append(row["id"])
    return ids
