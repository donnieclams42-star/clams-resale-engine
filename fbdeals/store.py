from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

from .config import settings

_lock = threading.RLock()
_DB_PATH = ""
_SEEDING = False

SCHEMA = """
CREATE TABLE IF NOT EXISTS marketplace_watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    query TEXT,
    location TEXT,
    radius_km INTEGER,
    min_price REAL,
    max_price REAL,
    category TEXT,
    condition TEXT,
    max_listing_age_days INTEGER,
    enabled INTEGER DEFAULT 1,
    min_expected_profit REAL,
    min_roi_pct REAL,
    alert_threshold TEXT,
    scan_interval_minutes INTEGER,
    excluded_terms TEXT,
    required_terms TEXT,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT,
    last_scan_at TEXT,
    next_scan_at TEXT
);
CREATE TABLE IF NOT EXISTS marketplace_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    external_listing_id TEXT,
    listing_url TEXT,
    title TEXT,
    asking_price REAL,
    currency TEXT,
    description TEXT,
    condition TEXT,
    category TEXT,
    location_text TEXT,
    city TEXT,
    state TEXT,
    latitude REAL,
    longitude REAL,
    seller_name TEXT,
    primary_image TEXT,
    image_urls TEXT,
    delivery_type TEXT,
    listed_at TEXT,
    first_seen_at TEXT,
    last_seen_at TEXT,
    scan_id INTEGER,
    watch_id INTEGER,
    raw_json TEXT,
    listing_status TEXT,
    last_event TEXT,
    ignored INTEGER DEFAULT 0,
    placeholder_price INTEGER DEFAULT 0,
    UNIQUE(source, external_listing_id)
);
CREATE TABLE IF NOT EXISTS listing_price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    asking_price REAL,
    event_type TEXT,
    recorded_at TEXT
);
CREATE TABLE IF NOT EXISTS deal_valuations (
    listing_id INTEGER PRIMARY KEY,
    expected_resale REAL,
    expected_net REAL,
    expected_profit REAL,
    roi_pct REAL,
    discount_pct REAL,
    break_even_price REAL,
    max_buy_price REAL,
    fees REAL,
    shipping REAL,
    confidence TEXT,
    deal_confidence TEXT,
    comp_confidence TEXT,
    classification TEXT,
    sold_count INTEGER,
    sold_median REAL,
    sold_average REAL,
    sold_low REAL,
    sold_high REAL,
    comp_source TEXT,
    reasons TEXT,
    reasons_json TEXT,
    signals_json TEXT,
    placeholder_price INTEGER,
    age_hours REAL,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS deal_comp_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    title TEXT,
    price REAL,
    sold_at TEXT,
    url TEXT,
    match_quality TEXT,
    source TEXT,
    condition TEXT
);
CREATE TABLE IF NOT EXISTS deal_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    alert_type TEXT,
    sent_at TEXT,
    price REAL,
    profit REAL,
    classification TEXT,
    channel TEXT,
    skip_reason TEXT,
    sent INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS deal_feedback (
    listing_id INTEGER PRIMARY KEY,
    action TEXT,
    purchase_price REAL,
    sale_price REAL,
    actual_costs REAL,
    actual_profit REAL,
    actual_roi REAL,
    predicted_resale REAL,
    predicted_profit REAL,
    notes TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id INTEGER,
    provider TEXT,
    status TEXT,
    started_at TEXT,
    finished_at TEXT,
    items_received INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    price_changes INTEGER DEFAULT 0,
    deep_analyzed INTEGER DEFAULT 0,
    qualified INTEGER DEFAULT 0,
    sms_sent INTEGER DEFAULT 0,
    rejected INTEGER DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    apify_run_id TEXT
);
CREATE TABLE IF NOT EXISTS listing_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER,
    title TEXT,
    description TEXT,
    category TEXT,
    condition TEXT,
    price REAL,
    min_price REAL,
    images TEXT,
    shipping_notes TEXT,
    keywords TEXT,
    status TEXT,
    open_marketplace_url TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_listings_watch ON marketplace_listings(watch_id);
CREATE INDEX IF NOT EXISTS idx_listings_event ON marketplace_listings(last_event);
CREATE INDEX IF NOT EXISTS idx_valuations_class ON deal_valuations(classification);
CREATE INDEX IF NOT EXISTS idx_alerts_listing ON deal_alerts(listing_id, sent_at);
CREATE INDEX IF NOT EXISTS idx_watches_next ON marketplace_watches(enabled, next_scan_at);
"""

JSON_KEYS = {
    "excluded_terms",
    "required_terms",
    "image_urls",
    "images",
    "keywords",
    "reasons",
    "reasons_json",
    "signals_json",
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(api[_-]?token|auth[_-]?token|secret|password|sid)([\"']?\s*[:=]\s*[\"']?)[^\"'\s,]+"),
    re.compile(r"AC[a-z0-9]{30,}"),
]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_db_path() -> str:
    cache_dir = os.getenv("RADAR_CACHE_DIR", "").strip()
    if not cache_dir:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cache_dir = os.path.join(root, "cache")
    return os.path.join(cache_dir, "marketplace.sqlite")


def set_db_path(path: str) -> None:
    global _DB_PATH
    _DB_PATH = os.path.abspath(str(path))
    parent = os.path.dirname(_DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)


def db_path() -> str:
    if not _DB_PATH:
        set_db_path(_default_db_path())
    return _DB_PATH


def redact(text: Any) -> str:
    value = str(text or "")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "***", value)
    for env_name in (
        "APIFY_API_TOKEN",
        "APIFY_TOKEN",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_ACCOUNT_SID",
        "TWILIO_API_KEY_SID",
        "TWILIO_API_KEY_SECRET",
        "TWILIO_MESSAGING_SERVICE_SID",
        "MARKET_RADAR_ALERT_TO_NUMBER",
        "EBAY_CLIENT_SECRET",
        "MARKET_RADAR_INGEST_SECRET",
        "APIFY_WEBHOOK_SECRET",
    ):
        secret = os.getenv(env_name, "")
        if secret:
            value = value.replace(secret, "***")
    return value


def _dumps(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _loads(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return [] if text == "" else value
    if text[:1] in "[{":
        try:
            return json.loads(text)
        except Exception:
            return value
    return value


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    data = dict(row)
    for key in JSON_KEYS:
        if key in data and isinstance(data[key], str):
            parsed = _loads(data[key])
            data[key] = parsed
    if isinstance(data.get("reasons_json"), list) and not data.get("reasons"):
        data["reasons"] = data["reasons_json"]
    if isinstance(data.get("reasons"), str) and data["reasons"][:1] in "[{":
        data["reasons"] = _loads(data["reasons"])
    return data


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def fetchall(sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        return [row_to_dict(row) for row in conn.execute(sql, tuple(params))]


def fetchone(sql: str, params: Iterable[Any] = ()) -> dict[str, Any]:
    with connect() as conn:
        return row_to_dict(conn.execute(sql, tuple(params)).fetchone())


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with connect() as conn:
        cur = conn.execute(sql, tuple(params))
        return int(cur.lastrowid or 0)


def _ensure_schema() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def init_db() -> str:
    path = db_path()
    _ensure_schema()
    _seed_default_watches()
    return path


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "", "None"):
            return default
        return int(float(value))
    except Exception:
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "None"):
            return default
        return float(value)
    except Exception:
        return default


def _as_enabled(value: Any, default: int = 1) -> int:
    if value is None or value == "":
        return default
    return 0 if str(value).strip().lower() in {"0", "false", "off", "no"} else 1


def _terms(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(part).strip() for part in value if str(part).strip()]
    text = str(value or "")
    if not text.strip():
        return []
    parsed = _loads(text)
    if isinstance(parsed, list):
        return [str(part).strip() for part in parsed if str(part).strip()]
    return [part.strip() for part in re.split(r"[,\n;]+", text) if part.strip()]


DEFAULT_WATCHES = [
    {"name": "PS5", "query": "PS5", "enabled": 1, "min_price": 40, "max_price": 500},
    {"name": "Xbox Series X", "query": "Xbox Series X", "enabled": 1, "min_price": 40, "max_price": 500},
    {"name": "Milwaukee tools", "query": "Milwaukee tools", "enabled": 1, "min_price": 20, "max_price": 800},
    {"name": "DeWalt tools", "query": "DeWalt tools", "enabled": 1, "min_price": 20, "max_price": 800},
    {"name": "gaming PC", "query": "gaming PC", "enabled": 1, "min_price": 80, "max_price": 2000},
    {"name": "iPhone", "query": "iPhone", "enabled": 1, "min_price": 40, "max_price": 900},
    {"name": "MacBook", "query": "MacBook", "enabled": 1, "min_price": 80, "max_price": 1800},
    {"name": "Pokemon", "query": "Pokemon", "enabled": 1, "min_price": 5, "max_price": 400},
    {"name": "Lego", "query": "Lego", "enabled": 1, "min_price": 10, "max_price": 500},
    {"name": "vintage", "query": "vintage", "enabled": 0, "min_price": 0, "max_price": 0},
    {"name": "electronics", "query": "electronics", "enabled": 0, "min_price": 0, "max_price": 0},
    {"name": "free", "query": "free", "enabled": 0, "min_price": 0, "max_price": 1},
    {"name": "moving sale", "query": "moving sale", "enabled": 0, "min_price": 0, "max_price": 0},
    {"name": "must go", "query": "must go", "enabled": 0, "min_price": 0, "max_price": 0},
    {"name": "need gone", "query": "need gone", "enabled": 0, "min_price": 0, "max_price": 0},
    {"name": "today only", "query": "today only", "enabled": 0, "min_price": 0, "max_price": 0},
]


def _seed_default_watches() -> None:
    global _SEEDING
    if _SEEDING:
        return
    existing = fetchone("SELECT COUNT(*) AS n FROM marketplace_watches")
    if int(existing.get("n") or 0) > 0:
        return
    _SEEDING = True
    cfg = settings()
    try:
        location = cfg.get("default_location") or "Atlantic City, New Jersey"
        radius = int(cfg.get("default_radius_km") or 80)
        interval = int(cfg.get("scan_interval_minutes") or 40)
        for item in DEFAULT_WATCHES:
            upsert_watch({
                **item,
                "location": location,
                "radius_km": radius,
                "scan_interval_minutes": interval,
                "min_expected_profit": 0 if item["query"] == "free" else 40,
                "min_roi_pct": 0 if item["query"] == "free" else 25,
                "alert_threshold": "BUY",
                "max_listing_age_days": 1,
            })
    finally:
        _SEEDING = False


def watches(enabled_only: bool = False) -> list[dict[str, Any]]:
    init_db()
    sql = "SELECT * FROM marketplace_watches"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY enabled DESC, name COLLATE NOCASE"
    return fetchall(sql)


def due_watches(limit: int | None = None) -> list[dict[str, Any]]:
    init_db()
    cfg = settings()
    cap = int(limit or cfg.get("max_watches_per_cycle") or 2)
    now = utcnow()
    rows = fetchall(
        """SELECT * FROM marketplace_watches
           WHERE enabled = 1 AND (next_scan_at IS NULL OR next_scan_at = '' OR next_scan_at <= ?)
           ORDER BY CASE WHEN next_scan_at IS NULL OR next_scan_at = '' THEN 0 ELSE 1 END, next_scan_at ASC
           LIMIT ?""",
        (now, cap),
    )
    return rows


def upsert_watch(payload: dict[str, Any]) -> int:
    if _SEEDING:
        _ensure_schema()
    else:
        init_db()
    now = utcnow()
    interval = payload.get("scan_interval_minutes")
    if interval in (None, ""):
        freq = payload.get("scan_frequency_seconds")
        interval = int(float(freq) / 60) if freq not in (None, "", 0, "0") else 40
    watch_id = _as_int(payload.get("id"), 0)
    data = {
        "name": str(payload.get("name") or payload.get("query") or "Watch").strip(),
        "query": str(payload.get("query") or payload.get("name") or "").strip(),
        "location": str(payload.get("location") or settings().get("default_location") or "Atlantic City, New Jersey"),
        "radius_km": _as_int(payload.get("radius_km"), 80),
        "min_price": _as_float(payload.get("min_price"), 0),
        "max_price": _as_float(payload.get("max_price"), 0),
        "category": str(payload.get("category") or ""),
        "condition": str(payload.get("condition") or "any"),
        "max_listing_age_days": _as_int(payload.get("max_listing_age_days"), 1),
        "enabled": _as_enabled(payload.get("enabled"), 1),
        "min_expected_profit": _as_float(payload.get("min_expected_profit"), 40),
        "min_roi_pct": _as_float(payload.get("min_roi_pct") if payload.get("min_roi_pct") not in (None, "") else payload.get("min_roi"), 25),
        "alert_threshold": str(payload.get("alert_threshold") or "BUY").upper(),
        "scan_interval_minutes": _as_int(interval, 40),
        "excluded_terms": _dumps(_terms(payload.get("excluded_terms"))),
        "required_terms": _dumps(_terms(payload.get("required_terms"))),
        "notes": str(payload.get("notes") or ""),
        "updated_at": now,
    }
    if data["scan_interval_minutes"] <= 0:
        data["scan_interval_minutes"] = 40
    if watch_id:
        existing = fetchone("SELECT id, created_at FROM marketplace_watches WHERE id = ?", (watch_id,))
        if existing:
            assignments = ", ".join(f"{key} = ?" for key in data)
            execute(
                f"UPDATE marketplace_watches SET {assignments} WHERE id = ?",
                list(data.values()) + [watch_id],
            )
            return watch_id
        data["created_at"] = now
        columns = ["id"] + list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        execute(
            f"INSERT INTO marketplace_watches ({', '.join(columns)}) VALUES ({placeholders})",
            [watch_id] + list(data.values()),
        )
        return watch_id
    data["created_at"] = now
    columns = list(data.keys())
    placeholders = ", ".join("?" for _ in columns)
    return execute(
        f"INSERT INTO marketplace_watches ({', '.join(columns)}) VALUES ({placeholders})",
        list(data.values()),
    )


def delete_watch(watch_id: int | str) -> None:
    execute("DELETE FROM marketplace_watches WHERE id = ?", (_as_int(watch_id),))


def mark_watch_scanned(watch_id: int | str, interval_minutes: int | str = 40) -> None:
    minutes = max(1, _as_int(interval_minutes, 40))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    from datetime import timedelta
    nxt = (now + timedelta(minutes=minutes)).isoformat()
    execute(
        "UPDATE marketplace_watches SET last_scan_at = ?, next_scan_at = ?, updated_at = ? WHERE id = ?",
        (now.isoformat(), nxt, now.isoformat(), _as_int(watch_id)),
    )


def create_scan_run(watch_id: Any, provider: str, status: str = "running", error_code: str = "", error_message: str = "") -> int:
    return execute(
        """INSERT INTO scan_runs (watch_id, provider, status, started_at, error_code, error_message)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (_as_int(watch_id), str(provider or ""), status, utcnow(), error_code, error_message),
    )


def update_scan_run(scan_id: Any, **kwargs: Any) -> None:
    if not kwargs:
        return
    fields = []
    values: list[Any] = []
    for key, value in kwargs.items():
        if not re.fullmatch(r"[A-Za-z_]+", str(key)):
            continue
        fields.append(f"{key} = ?")
        values.append(value)
    if "finished_at" not in kwargs and str(kwargs.get("status") or "") in {"completed", "error", "zero_results"}:
        fields.append("finished_at = ?")
        values.append(utcnow())
    values.append(_as_int(scan_id))
    execute(f"UPDATE scan_runs SET {', '.join(fields)} WHERE id = ?", values)


def latest_scan() -> dict[str, Any]:
    return fetchone("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1")


def listing_by_external(source: str, external_id: str) -> dict[str, Any]:
    return fetchone(
        "SELECT * FROM marketplace_listings WHERE source = ? AND external_listing_id = ?",
        (source, str(external_id or "")),
    )


def listing_by_id(listing_id: Any) -> dict[str, Any]:
    return fetchone("SELECT * FROM marketplace_listings WHERE id = ?", (_as_int(listing_id),))


def save_listing(record: dict[str, Any], event_type: str, scan_id: Any = "") -> tuple[int, str]:
    source = str(record.get("source") or "facebook_marketplace")
    external = str(record.get("external_listing_id") or "")
    existing = listing_by_external(source, external) if external else {}
    now = utcnow()
    event = str(event_type or "NEW_LISTING")
    listing_id = _as_int(existing.get("id"), 0)
    payload = {
        "source": source,
        "external_listing_id": external,
        "listing_url": record.get("listing_url") or "",
        "title": record.get("title") or "",
        "asking_price": record.get("asking_price"),
        "currency": record.get("currency") or "USD",
        "description": record.get("description") or existing.get("description") or "",
        "condition": record.get("condition") or existing.get("condition") or "",
        "category": record.get("category") or "",
        "location_text": record.get("location_text") or "",
        "city": record.get("city") or "",
        "state": record.get("state") or "",
        "latitude": record.get("latitude"),
        "longitude": record.get("longitude"),
        "seller_name": record.get("seller_name") or existing.get("seller_name") or "",
        "primary_image": record.get("primary_image") or existing.get("primary_image") or "",
        "image_urls": _dumps(record.get("image_urls") or []),
        "delivery_type": record.get("delivery_type") or "",
        "listed_at": record.get("listed_at") or existing.get("listed_at") or "",
        "first_seen_at": existing.get("first_seen_at") or now,
        "last_seen_at": now,
        "scan_id": _as_int(scan_id or record.get("scan_id"), 0) or None,
        "watch_id": _as_int(record.get("watch_id") or existing.get("watch_id"), 0) or None,
        "raw_json": record.get("raw_json") or existing.get("raw_json") or "",
        "listing_status": record.get("listing_status") or "live",
        "last_event": event,
        "ignored": existing.get("ignored") or 0,
        "placeholder_price": 1 if record.get("placeholder_price") else 0,
    }
    if listing_id:
        assignments = ", ".join(f"{key} = ?" for key in payload if key not in {"source", "external_listing_id", "first_seen_at"})
        values = [payload[key] for key in payload if key not in {"source", "external_listing_id", "first_seen_at"}]
        execute(
            f"UPDATE marketplace_listings SET {assignments} WHERE id = ?",
            values + [listing_id],
        )
    else:
        columns = list(payload.keys())
        execute(
            f"INSERT INTO marketplace_listings ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            [payload[key] for key in columns],
        )
        listing_id = _as_int(listing_by_external(source, external).get("id"))
    if event in {"NEW_LISTING", "PRICE_DROP", "PRICE_INCREASE"} and payload["asking_price"] is not None:
        execute(
            "INSERT INTO listing_price_history (listing_id, asking_price, event_type, recorded_at) VALUES (?, ?, ?, ?)",
            (listing_id, payload["asking_price"], event, now),
        )
    return listing_id, event


def save_valuation(listing_id: Any, valuation: dict[str, Any]) -> None:
    lid = _as_int(listing_id)
    reasons = valuation.get("reasons") or []
    payload = {
        "listing_id": lid,
        "expected_resale": valuation.get("expected_resale"),
        "expected_net": valuation.get("expected_net"),
        "expected_profit": valuation.get("expected_profit"),
        "roi_pct": valuation.get("roi_pct", valuation.get("roi")),
        "discount_pct": valuation.get("discount_pct"),
        "break_even_price": valuation.get("break_even_price", valuation.get("break_even")),
        "max_buy_price": valuation.get("max_buy_price", valuation.get("max_buy")),
        "fees": valuation.get("fees", valuation.get("fee_estimate")),
        "shipping": valuation.get("shipping", valuation.get("shipping_estimate")),
        "confidence": valuation.get("confidence") or valuation.get("deal_confidence") or valuation.get("comp_confidence") or "",
        "deal_confidence": valuation.get("deal_confidence") or valuation.get("confidence") or "",
        "comp_confidence": valuation.get("comp_confidence") or valuation.get("confidence") or "",
        "classification": valuation.get("classification") or "",
        "sold_count": valuation.get("sold_count") or 0,
        "sold_median": valuation.get("sold_median"),
        "sold_average": valuation.get("sold_average"),
        "sold_low": valuation.get("sold_low"),
        "sold_high": valuation.get("sold_high"),
        "comp_source": valuation.get("comp_source") or valuation.get("valuation_source") or "",
        "reasons": _dumps(reasons),
        "reasons_json": _dumps(valuation.get("reasons_json") if valuation.get("reasons_json") is not None else reasons),
        "signals_json": _dumps(valuation.get("signals_json") if valuation.get("signals_json") is not None else valuation.get("signals") or []),
        "placeholder_price": 1 if valuation.get("placeholder_price") else 0,
        "age_hours": valuation.get("age_hours"),
        "updated_at": utcnow(),
    }
    columns = list(payload.keys())
    updates = ", ".join(f"{key}=excluded.{key}" for key in columns if key != "listing_id")
    execute(
        f"INSERT INTO deal_valuations ({', '.join(columns)}) VALUES ({', '.join(':' + k if False else '?' for k in columns)}) "
        f"ON CONFLICT(listing_id) DO UPDATE SET {updates}",
        [payload[key] for key in columns],
    )


def replace_comps(listing_id: Any, comps: list[dict[str, Any]] | None) -> None:
    lid = _as_int(listing_id)
    execute("DELETE FROM deal_comp_records WHERE listing_id = ?", (lid,))
    for comp in (comps or [])[:40]:
        execute(
            """INSERT INTO deal_comp_records (listing_id, title, price, sold_at, url, match_quality, source, condition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lid,
                comp.get("title") or "",
                comp.get("price"),
                comp.get("sold_at") or "",
                comp.get("url") or "",
                comp.get("match_quality") or "",
                comp.get("source") or "",
                comp.get("condition") or "",
            ),
        )


def latest_valuation(listing_id: Any) -> dict[str, Any]:
    return fetchone("SELECT * FROM deal_valuations WHERE listing_id = ?", (_as_int(listing_id),))


def price_history(listing_id: Any) -> list[dict[str, Any]]:
    return fetchall(
        "SELECT * FROM listing_price_history WHERE listing_id = ? ORDER BY recorded_at ASC, id ASC",
        (_as_int(listing_id),),
    )


def comps_for(listing_id: Any) -> list[dict[str, Any]]:
    return fetchall("SELECT * FROM deal_comp_records WHERE listing_id = ? ORDER BY price ASC", (_as_int(listing_id),))


def record_alert(
    listing_id: Any,
    alert_type: str,
    price: Any = None,
    profit: Any = None,
    classification: str = "",
    channel: str = "sms",
    skip_reason: str = "",
    sent: bool = True,
    **kwargs: Any,
) -> int:
    return execute(
        """INSERT INTO deal_alerts (listing_id, alert_type, sent_at, price, profit, classification, channel, skip_reason, sent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _as_int(listing_id),
            alert_type,
            utcnow(),
            price if price is not None else kwargs.get("price_at_alert"),
            profit if profit is not None else kwargs.get("profit_at_alert"),
            classification,
            channel,
            skip_reason,
            1 if sent and not skip_reason else 0,
        ),
    )


def alerts_for(listing_id: Any) -> list[dict[str, Any]]:
    return fetchall("SELECT * FROM deal_alerts WHERE listing_id = ? ORDER BY id DESC", (_as_int(listing_id),))


def recent_alerts(hours: int = 24, channel: str = "sms", sent_only: bool = True) -> list[dict[str, Any]]:
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1, int(hours)))).replace(microsecond=0).isoformat()
    sql = "SELECT * FROM deal_alerts WHERE channel = ? AND sent_at >= ?"
    params: list[Any] = [channel, cutoff]
    if sent_only:
        sql += " AND sent = 1 AND (skip_reason IS NULL OR skip_reason = '')"
    sql += " ORDER BY id DESC"
    return fetchall(sql, params)


def save_feedback(listing_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    lid = _as_int(listing_id)
    data = {
        "listing_id": lid,
        "action": str(payload.get("action") or ""),
        "purchase_price": payload.get("purchase_price"),
        "sale_price": payload.get("sale_price"),
        "actual_costs": payload.get("actual_costs") if payload.get("actual_costs") is not None else payload.get("costs"),
        "actual_profit": payload.get("actual_profit"),
        "actual_roi": payload.get("actual_roi"),
        "predicted_resale": payload.get("predicted_resale"),
        "predicted_profit": payload.get("predicted_profit"),
        "notes": payload.get("notes") or "",
        "created_at": utcnow(),
    }
    columns = list(data.keys())
    updates = ", ".join(f"{key}=excluded.{key}" for key in columns if key != "listing_id")
    execute(
        f"INSERT INTO deal_feedback ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT(listing_id) DO UPDATE SET {updates}",
        [data[key] for key in columns],
    )
    if str(data["action"]).upper() == "IGNORE":
        execute("UPDATE marketplace_listings SET ignored = 1 WHERE id = ?", (lid,))
    return fetchone("SELECT * FROM deal_feedback WHERE listing_id = ?", (lid,))


def save_listing_draft(listing_id: Any, draft: dict[str, Any]) -> dict[str, Any]:
    lid = _as_int(listing_id)
    execute("DELETE FROM listing_drafts WHERE listing_id = ?", (lid,))
    execute(
        """INSERT INTO listing_drafts (listing_id, title, description, category, condition, price, min_price, images,
           shipping_notes, keywords, status, open_marketplace_url, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            lid,
            draft.get("title") or "",
            draft.get("description") or "",
            draft.get("category") or "",
            draft.get("condition") or "",
            draft.get("price"),
            draft.get("min_price"),
            _dumps(draft.get("images") or []),
            draft.get("shipping_notes") or "",
            _dumps(draft.get("keywords") or []),
            draft.get("status") or "READY_TO_POST",
            draft.get("open_marketplace_url") or "https://www.facebook.com/marketplace/create/item",
            utcnow(),
        ),
    )
    return listing_draft(lid)


def listing_draft(listing_id: Any) -> dict[str, Any]:
    return fetchone(
        "SELECT * FROM listing_drafts WHERE listing_id = ? ORDER BY id DESC LIMIT 1",
        (_as_int(listing_id),),
    )


def _class_rank(value: str) -> int:
    return {"HOT": 0, "BUY": 1, "WATCH": 2, "RISK": 3, "PASS": 4}.get(str(value or "").upper(), 5)


def deal_feed(filters: dict[str, Any] | None = None, limit: int = 80) -> list[dict[str, Any]]:
    filters = filters or {}
    sql = """SELECT listings.*,
             vals.expected_resale, vals.expected_net, vals.expected_profit, vals.roi_pct,
             vals.discount_pct, vals.break_even_price, vals.max_buy_price, vals.fees, vals.shipping,
             vals.confidence, vals.deal_confidence, vals.comp_confidence, vals.classification,
             vals.sold_count, vals.reasons, vals.reasons_json, vals.signals_json, vals.placeholder_price AS val_placeholder,
             vals.comp_source, vals.age_hours
             FROM marketplace_listings AS listings
             LEFT JOIN deal_valuations AS vals ON listings.id = vals.listing_id
             WHERE COALESCE(listings.ignored, 0) = 0"""
    args: list[Any] = []
    classification = str(filters.get("classification") or "").upper()
    if classification and classification not in {"", "ALL"}:
        sql += " AND UPPER(vals.classification) = ?"
        args.append(classification)
    if filters.get("watch_id"):
        sql += " AND listings.watch_id = ?"
        args.append(_as_int(filters["watch_id"]))
    if filters.get("new") in {1, "1", True, "true", "yes"}:
        sql += " AND listings.last_event = 'NEW_LISTING'"
    if filters.get("price_drops") in {1, "1", True, "true", "yes"} or filters.get("event") == "PRICE_DROP":
        sql += " AND listings.last_event = 'PRICE_DROP'"
    if filters.get("min_profit"):
        sql += " AND vals.expected_profit >= ?"
        args.append(_as_float(filters["min_profit"]))
    if filters.get("min_roi"):
        sql += " AND vals.roi_pct >= ?"
        args.append(_as_float(filters["min_roi"]))
    if filters.get("location"):
        sql += " AND listings.location_text LIKE ?"
        args.append(f"%{filters['location']}%")
    sort = str(filters.get("sort") or "best").lower()
    if sort == "newest":
        sql += " ORDER BY listings.first_seen_at DESC"
    elif sort == "profit":
        sql += " ORDER BY vals.expected_profit DESC"
    elif sort == "roi":
        sql += " ORDER BY vals.roi_pct DESC"
    elif sort == "price_drop":
        sql += " ORDER BY CASE listings.last_event WHEN 'PRICE_DROP' THEN 0 ELSE 1 END, listings.last_seen_at DESC"
    elif sort == "nearest":
        sql += " ORDER BY listings.location_text COLLATE NOCASE"
    else:
        sql += " ORDER BY CASE vals.classification WHEN 'HOT' THEN 0 WHEN 'BUY' THEN 1 WHEN 'WATCH' THEN 2 WHEN 'RISK' THEN 3 ELSE 4 END, vals.expected_profit DESC"
    sql += " LIMIT ?"
    args.append(int(limit or 80))
    rows = fetchall(sql, args)
    emojis = {"HOT": "🔥", "BUY": "✅", "WATCH": "👀", "RISK": "⚠️", "PASS": "⛔"}
    for row in rows:
        row["class_emoji"] = emojis.get(str(row.get("classification") or "").upper(), "👀")
        if isinstance(row.get("reasons_json"), list) and not row.get("reasons"):
            row["reasons"] = row["reasons_json"]
        row["fee_estimate"] = row.get("fees")
        row["shipping_estimate"] = row.get("shipping")
        if row.get("val_placeholder"):
            row["placeholder_price"] = row.get("val_placeholder")
    return rows


def dashboard_counts() -> dict[str, Any]:
    init_db()
    enabled = fetchone("SELECT COUNT(*) AS n FROM marketplace_watches WHERE enabled = 1")
    new_listings = fetchone("SELECT COUNT(*) AS n FROM marketplace_listings WHERE last_event = 'NEW_LISTING' AND COALESCE(ignored,0)=0")
    hot = fetchone("SELECT COUNT(*) AS n FROM deal_valuations WHERE classification = 'HOT'")
    buy = fetchone("SELECT COUNT(*) AS n FROM deal_valuations WHERE classification = 'BUY'")
    next_row = fetchone(
        "SELECT MIN(next_scan_at) AS next_scan_at FROM marketplace_watches WHERE enabled = 1 AND next_scan_at IS NOT NULL AND next_scan_at != ''"
    )
    return {
        "enabled_watches": int(enabled.get("n") or 0),
        "new_listings": int(new_listings.get("n") or 0),
        "hot": int(hot.get("n") or 0),
        "buy": int(buy.get("n") or 0),
        "last_scan": latest_scan() or {},
        "next_scan_at": next_row.get("next_scan_at") or "",
        "listings": int(fetchone("SELECT COUNT(*) AS n FROM marketplace_listings WHERE COALESCE(ignored,0)=0").get("n") or 0),
        "watches": int(enabled.get("n") or 0),
    }
